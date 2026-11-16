from pydantic import BaseModel


class CollectionStats(BaseModel):
    collected_count: int = 0
    created_count: int = 0
    updated_count: int = 0
    unchanged_count: int = 0
    rejected_count: int = 0
    failed_count: int = 0
    adapter_rejected_stale: int = 0
    adapter_rejected_unknown_posting: int = 0
    adapter_rejected_location_mismatch: int = 0
    adapter_rejected_keyword_mismatch: int = 0

    def merge(self, other: "CollectionStats") -> None:
        self.collected_count += other.collected_count
        self.created_count += other.created_count
        self.updated_count += other.updated_count
        self.unchanged_count += other.unchanged_count
        self.rejected_count += other.rejected_count
        self.failed_count += other.failed_count
        self.adapter_rejected_stale += other.adapter_rejected_stale
        self.adapter_rejected_unknown_posting += other.adapter_rejected_unknown_posting
        self.adapter_rejected_location_mismatch += other.adapter_rejected_location_mismatch
        self.adapter_rejected_keyword_mismatch += other.adapter_rejected_keyword_mismatch
