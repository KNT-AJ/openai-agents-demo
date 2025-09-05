from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class InvoiceLineItem:
    description: str
    quantity: Optional[float] = None
    unit: Optional[str] = None
    unit_price: Optional[float] = None
    amount: Optional[float] = None


@dataclass
class Invoice:
    invoice_number: Optional[str] = None
    invoice_date: Optional[str] = None  # ISO date string if available
    vendor_name: Optional[str] = None
    vendor_address: Optional[str] = None
    buyer_name: Optional[str] = None
    buyer_address: Optional[str] = None
    currency: Optional[str] = None
    subtotal: Optional[float] = None
    tax: Optional[float] = None
    total: Optional[float] = None
    due_date: Optional[str] = None
    po_number: Optional[str] = None
    line_items: List[InvoiceLineItem] = field(default_factory=list)

