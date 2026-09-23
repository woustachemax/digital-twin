import re
from typing import List, Dict, Optional, Any


AMOUNT_RE = r'(?:Rs\.?|INR)\s*([0-9,]+(?:\.[0-9]{1,2})?)'
TXN_TYPE_RE = r'\b(debited|credited|spent|debit|credit)\b'
VPA_RE = r'\b([\w.\-]+@[a-zA-Z]+)\b'
MERCHANT_AT_RE = r'\bat\s+([A-Za-z0-9&\.\-\_ ]+?)\s+using\b'
REF_RE = r'\b(?:Ref\.?\s*No\.?|RRN|UPI\s*Ref(?:erence)?(?:\s*No)?\.?|Txn\s*ID)\s*[:\-]?\s*([A-Za-z0-9]+)'


def _normalize_amount(raw: str) -> float:
    return float(raw.replace(',', ''))


def _extract_type(text: str) -> Optional[str]:
    match = re.search(TXN_TYPE_RE, text, re.IGNORECASE)
    if not match:
        return None
    word = match.group(1).lower()
    if word in ('debited', 'debit', 'spent'):
        return 'debited'
    if word in ('credited', 'credit'):
        return 'credited'
    return None


def _extract_amount(text: str) -> Optional[float]:
    match = re.search(AMOUNT_RE, text, re.IGNORECASE)
    if not match:
        return None
    return _normalize_amount(match.group(1))


def _extract_merchant(text: str) -> Optional[str]:
    vpa_match = re.search(VPA_RE, text)
    if vpa_match:
        return vpa_match.group(1)
    merchant_match = re.search(MERCHANT_AT_RE, text, re.IGNORECASE)
    if merchant_match:
        return merchant_match.group(1).strip()
    return None


def _extract_reference(text: str) -> Optional[str]:
    match = re.search(REF_RE, text, re.IGNORECASE)
    if not match:
        return None
    return match.group(1)


def parse_transaction_message(text: str) -> Optional[Dict[str, Any]]:
    txn_type = _extract_type(text)
    amount = _extract_amount(text)
    if txn_type is None or amount is None:
        return None
    return {
        'type': txn_type,
        'amount': amount,
        'merchant': _extract_merchant(text),
        'reference': _extract_reference(text),
    }


def parse_messages(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    results = []
    for message in messages:
        text = message.get('text', '')
        parsed = parse_transaction_message(text)
        if parsed is None:
            continue
        results.append({
            'timestamp': message.get('timestamp'),
            'sender': message.get('sender'),
            **parsed,
        })
    return results


if __name__ == '__main__':
    sample_messages = [
        {
            'text': "Rs.450.00 debited from A/c XX1234 on 23-Sep-26 to VPA merchant@upi. Avl Bal Rs.12,340.50",
            'timestamp': '2026-09-23T10:00:00',
            'sender': 'HDFCBK',
        },
        {
            'text': "You've spent Rs.1200 at SWIGGY using UPI. Ref No 402913948291",
            'timestamp': '2026-09-23T12:30:00',
            'sender': 'ICICIB',
        },
        {
            'text': "INR 300 credited to your account XX1234 on 23-09-2026",
            'timestamp': '2026-09-23T14:15:00',
            'sender': 'SBIINB',
        },
    ]

    for txn in parse_messages(sample_messages):
        print(txn)
