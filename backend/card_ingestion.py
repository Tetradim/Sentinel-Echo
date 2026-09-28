"""Bind card exits to their source position and persist stable action identities."""
import hashlib
import json

from position_identity import canonical_expiration_yyyymmdd, same_option_contract


async def prepare_card(db, parsed: dict, channel_id: str, message_id: str, settings: dict) -> tuple[dict, str]:
    parsed = dict(parsed)
    card = dict(parsed['_card'])
    if db is None:
        return parsed, 'card ingestion database unavailable'
    if not channel_id or not message_id:
        return parsed, 'card requires source channel and message identity'
    cycle = message_id
    if parsed['alert_type'] != 'buy':
        positions = await db.get_positions('open') + await db.get_positions('partial')
        matches = []
        for position in positions:
            if str(position.get('broker') or '').lower() != str(settings.get('active_broker') or 'alpaca').lower():
                continue
            candidate = {**parsed, 'expiration': parsed.get('expiration') or position.get('expiration')}
            if not same_option_contract(candidate, position):
                continue
            origin = await db.get_alert_by_id(str(position.get('alert_id') or ''))
            if not origin or str(origin.get('channel_id') or '') != channel_id:
                continue
            if float(position.get('remaining_quantity', position.get('quantity', 0)) or 0) > 0:
                matches.append(position)
        if len(matches) != 1:
            return parsed, 'card exit has no matching source position' if not matches else 'card exit matches multiple source positions'
        position = matches[0]
        parsed['expiration'] = position['expiration']
        card['position_id'] = position['id']
        cycle = str(position['alert_id'])
    # Edits and separate update posts share identity; a later entry starts a new cycle.
    identity = [channel_id, cycle, parsed['ticker'], parsed['strike'], parsed['option_type'],
                canonical_expiration_yyyymmdd(parsed['expiration']), parsed['alert_type'],
                parsed.get('sell_percentage'), card.get('reported_exit_price')]
    card['action_id'] = 'card-' + hashlib.sha256(json.dumps(identity, separators=(',', ':')).encode()).hexdigest()
    parsed['_card'] = card
    return parsed, ''
