import logging
import time
from decimal import Decimal

from azure.ai.documentintelligence.aio import DocumentIntelligenceClient
from azure.ai.documentintelligence.models import (
    AnalyzeDocumentRequest,
    AnalyzeResult,
    DocumentFigure,
    DocumentPage,
    DocumentTable,
)
from azure.core.credentials import AzureKeyCredential
from azure.core.exceptions import AzureError, HttpResponseError

from providers.exceptions import (
    OcrError,
    OcrServiceError,
    OcrTransientError,
    OcrValidationError,
)
from providers.models import (
    AzureDocumentIntelligenceConfig,
    FigureElement,
    ModelBasicInfo,
    OcrPageElement,
    OcrResponse,
    TableCell,
    TableElement,
    WordElement,
)
from providers.ocr.base import BaseOCR

logger = logging.getLogger(__name__)


class DocumentIntelligenceExtractor(BaseOCR):
    """Azure Document Intelligence OCR extractor."""

    def __init__(
        self,
        model_info: ModelBasicInfo,
        config: AzureDocumentIntelligenceConfig | None = None,
    ) -> None:
        self.config = config if config is not None else AzureDocumentIntelligenceConfig()
        super().__init__(self.config.min_ocr_confidence)

        endpoint = model_info.secret.api_endpoint
        key = model_info.secret.api_key

        if not endpoint or not key:
            raise OcrValidationError(
                "Azure Document Intelligence endpoint and key are required",
                "OCR service configuration is missing required credentials.",
            )

        if not endpoint.startswith("https://"):
            raise OcrValidationError(
                f"Invalid endpoint format: {endpoint}. Must start with https://",
                "OCR service endpoint must use HTTPS protocol.",
            )

        self.endpoint = endpoint
        self.key = key
        self.model_name = model_info.model_name

        self.document_intelligence_client = DocumentIntelligenceClient(
            endpoint=self.endpoint, credential=AzureKeyCredential(self.key)
        )

        self._word_id_counter: int = 0

        logger.info(
            f"Initialised DocumentIntelligenceExtractor with model={self.model_name}, "
            f"min_confidence={self.config.min_ocr_confidence}, model_id={self.config.model_id}"
        )

    async def extract(self, document: bytes) -> OcrResponse:
        if not document:
            raise OcrValidationError(
                "Document bytes cannot be empty",
                "The document file appears to be empty or corrupted.",
            )

        try:
            logger.info("Starting Document Intelligence extraction")
            analyze_result = await self._get_raw_results(document)

            if not analyze_result or not analyze_result.pages:
                logger.warning("No content found in document")
                return OcrResponse(
                    no_pages=0, raw_ocr={}, page_elements=[], duration=Decimal("0.0")
                )

            start_time = time.time()
            page_elements = self._process_analyze_result(analyze_result)
            duration = time.time() - start_time

            response = OcrResponse(
                no_pages=len(analyze_result.pages),
                raw_ocr=analyze_result.as_dict(),
                page_elements=page_elements,
                duration=Decimal(str(duration)),
            )

            logger.info(
                f"Extraction completed: {len(page_elements)} pages, "
                f"{sum(len(p.words) for p in page_elements)} words, "
                f"{sum(len(p.tables) for p in page_elements)} tables, "
                f"{sum(len(p.figures) for p in page_elements)} figures"
            )
            return response

        except OcrError:
            raise
        except Exception as e:
            logger.error(f"Unexpected error in extract method: {e}")
            raise OcrServiceError(
                f"OCR extraction failed: {str(e)}",
                "An unexpected error occurred during OCR processing",
            ) from e

    async def _get_raw_results(self, document_bytes: bytes) -> AnalyzeResult:
        logger.info("Calling Document Intelligence service")

        try:
            request = AnalyzeDocumentRequest(bytes_source=document_bytes)
            poller = await self.document_intelligence_client.begin_analyze_document(
                model_id=self.config.model_id, body=request
            )
            result = await poller.result()
            logger.info("Received result from Document Intelligence")
            return result

        except HttpResponseError as e:
            status_code = getattr(e, "status_code", 0)
            if status_code == 401:
                raise OcrValidationError(
                    f"Document Intelligence authentication failed: {e}",
                    "Invalid credentials for OCR service.",
                )
            if status_code == 403:
                raise OcrValidationError(
                    f"Document Intelligence access forbidden: {e}",
                    "Access denied to OCR service.",
                )
            if status_code == 413:
                raise OcrValidationError(
                    f"Document Intelligence document too large: {e}",
                    "Document is too large for processing.",
                )
            if status_code == 415:
                raise OcrValidationError(
                    f"Document Intelligence unsupported format: {e}",
                    "Document format is not supported.",
                )
            if status_code == 429:
                raise OcrTransientError(
                    f"Document Intelligence rate limit exceeded: {e}",
                    "OCR service rate limit exceeded.",
                )
            raise OcrServiceError(
                f"Document Intelligence API error ({status_code}): {e}",
                "OCR service error occurred.",
            )

        except AzureError as e:
            logger.error(f"Azure Document Intelligence API call failed: {e}")
            raise OcrServiceError(
                f"Azure service failed: {e}",
                "The OCR service encountered an Azure-related error.",
            )
        except Exception as e:
            logger.error(f"Unexpected error in Document Intelligence: {e}", exc_info=True)
            raise OcrServiceError(
                f"Unexpected OCR processing error: {e}",
                "An unexpected error occurred.",
            )

    def _process_analyze_result(
        self, analyze_result: AnalyzeResult
    ) -> list[OcrPageElement]:
        processed_pages: list[OcrPageElement] = []
        self._word_id_counter = 0

        for page_data in analyze_result.pages:
            logger.debug(f"Processing page {page_data.page_number}")

            page_width = page_data.width if page_data.width and page_data.width > 0 else 1.0
            page_height = (
                page_data.height if page_data.height and page_data.height > 0 else 1.0
            )

            page_words = self._process_page_words(page_data, page_width, page_height)
            page_tables = self._process_page_tables(
                page_data, page_width, page_height, analyze_result.tables
            )
            page_figures = self._process_page_figures(
                page_data, page_width, page_height, analyze_result.figures
            )

            ocr_page = OcrPageElement(
                page=page_data.page_number,
                page_width=Decimal(str(page_width)),
                page_height=Decimal(str(page_height)),
                words=page_words,
                tables=page_tables,
                figures=page_figures,
            )
            processed_pages.append(ocr_page)

        return processed_pages

    def _polygon_to_bounding_box(self, polygon: list[float]) -> list[float]:
        if not polygon or len(polygon) < 8:
            return [0.0, 0.0, 0.0, 0.0]
        x_coords = polygon[0::2]
        y_coords = polygon[1::2]
        return [min(x_coords), min(y_coords), max(x_coords), max(y_coords)]

    def _normalize_box(
        self, box: list[float], page_width: float, page_height: float
    ) -> list[float]:
        if not box or len(box) < 4:
            return [0.0, 0.0, 0.0, 0.0]
        return [
            round(box[0] / page_width, 4),
            round(box[1] / page_height, 4),
            round(box[2] / page_width, 4),
            round(box[3] / page_height, 4),
        ]

    def _process_page_words(
        self, page_data: DocumentPage, page_width: float, page_height: float
    ) -> list[WordElement]:
        if not page_data.words:
            return []

        word_elements: list[WordElement] = []
        for word in page_data.words:
            confidence = word.confidence if word.confidence is not None else 1.0
            if confidence < (self.min_ocr_confidence / 100.0) or not word.polygon:
                continue

            abs_box = self._polygon_to_bounding_box(word.polygon)
            norm_box = self._normalize_box(abs_box, page_width, page_height)

            word_elements.append(
                WordElement(
                    id=self._word_id_counter,
                    text=word.content,
                    conf=Decimal(str(confidence)),
                    box=[Decimal(str(coord)) for coord in norm_box],
                )
            )
            self._word_id_counter += 1

        return word_elements

    def _process_page_tables(
        self,
        page_data: DocumentPage,
        page_width: float,
        page_height: float,
        all_tables: list[DocumentTable] | None = None,
    ) -> list[TableElement]:
        if not all_tables:
            return []

        table_elements: list[TableElement] = []

        page_tables: list[DocumentTable] = []
        for table in all_tables:
            if table.bounding_regions:
                for region in table.bounding_regions:
                    if region.page_number == page_data.page_number:
                        page_tables.append(table)
                        break

        for table in page_tables:
            cells: list[TableCell] = []

            for cell_data in table.cells:
                cell_box = None
                if cell_data.bounding_regions:
                    abs_box = self._polygon_to_bounding_box(
                        cell_data.bounding_regions[0].polygon
                    )
                    cell_box = self._normalize_box(abs_box, page_width, page_height)

                cells.append(
                    TableCell(
                        row=cell_data.row_index,
                        col=cell_data.column_index,
                        row_span=cell_data.row_span or 1,
                        col_span=cell_data.column_span or 1,
                        kind=cell_data.kind,
                        text=cell_data.content or "",
                        box=[Decimal(str(coord)) for coord in cell_box] if cell_box else None,
                    )
                )

            table_box = None
            if table.bounding_regions:
                for region in table.bounding_regions:
                    if region.page_number == page_data.page_number:
                        abs_box = self._polygon_to_bounding_box(region.polygon)
                        table_box = self._normalize_box(abs_box, page_width, page_height)
                        break

            table_elements.append(
                TableElement(
                    rows=table.row_count,
                    cols=table.column_count,
                    cells=cells,
                    box=[Decimal(str(coord)) for coord in table_box] if table_box else None,
                )
            )

        return table_elements

    def _process_page_figures(
        self,
        page_data: DocumentPage,
        page_width: float,
        page_height: float,
        all_figures: list[DocumentFigure] | None = None,
    ) -> list[FigureElement]:
        if not all_figures:
            return []

        figure_elements: list[FigureElement] = []
        page_figures: list[DocumentFigure] = []
        for figure in all_figures:
            if figure.bounding_regions:
                for region in figure.bounding_regions:
                    if region.page_number == page_data.page_number:
                        page_figures.append(figure)
                        break

        for figure in page_figures:
            try:
                caption_text = None
                if figure.caption:
                    caption_text = figure.caption.content

                figure_box = None
                if figure.bounding_regions:
                    for region in figure.bounding_regions:
                        if region.page_number == page_data.page_number:
                            abs_box = self._polygon_to_bounding_box(region.polygon)
                            figure_box = self._normalize_box(
                                abs_box, page_width, page_height
                            )
                            break

                figure_element = FigureElement(
                    caption=caption_text,
                    box=[Decimal(str(coord)) for coord in figure_box] if figure_box else None,
                )

                figure_elements.append(figure_element)
            except Exception as e:
                logger.warning(f"Error processing figure: {e}")
                continue

        return figure_elements

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.document_intelligence_client.close()
