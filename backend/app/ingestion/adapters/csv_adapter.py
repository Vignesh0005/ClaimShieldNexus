import csv
import io
from collections.abc import AsyncIterator

from app.ingestion.adapters.base import IngestionAdapter
from app.ingestion.field_mapping import apply_mapping
from app.ingestion.normalizer import rows_to_claims


class CSVAdapter(IngestionAdapter):
    """One row per service line. Rows sharing a claim ID are grouped into one claim."""

    name = "csv"

    def __init__(self, text: str, mapping: dict[str, str] | None = None):
        self.text = text
        self.mapping = mapping

    def parse(self) -> list[dict]:
        sample = self.text[:4096]
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
        except csv.Error:
            dialect = csv.excel
        reader = csv.DictReader(io.StringIO(self.text), dialect=dialect)
        rows = [apply_mapping({(k or "").strip(): (v or "").strip() for k, v in row.items()}, self.mapping) for row in reader]
        return rows_to_claims(rows)

    async def records(self) -> AsyncIterator[dict]:
        for claim in self.parse():
            yield claim
