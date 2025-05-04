import aiohttp
import asyncio
from typing import Dict, List, Any

class DeckChecker:
    """Async MTG deck legality checker with proper rate limiting."""
    
    UNLIMITED_CARDS = {
        "Persistent Petitioners", "Rat Colony", "Relentless Rats",
        "Shadowborn Apostle", "Dragon's Approach"
    }
    
    SPECIAL_LIMIT_CARDS = {"Seven Dwarves": 7}
    SCRYFALL_DELAY = 0.1  # 100ms delay between requests

    def __init__(self, deck: Dict[str, Any], deck_format: str):
        self.deck = deck
        self.format = deck_format
        self.reasons: List[str] = []
        self._rate_limit_semaphore = asyncio.Semaphore(10)

    async def check_deck_size(self) -> None:
        """Validate deck size requirements by actually counting cards."""
        main_count = sum(c["quantity"] for c in self.deck.get("maindeck", []))
        side_count = sum(c["quantity"] for c in self.deck.get("sidedeck", []))
        
        if self.format == "commander":
            if main_count != 99:
                self.reasons.append(f"Commander deck has {main_count}/99 cards")
            if side_count != 1:
                self.reasons.append(f"Has {side_count} commanders (needs 1)")
        else:
            if main_count < 60:
                self.reasons.append(f"Maindeck has {main_count}/60 cards")
            if side_count > 15:
                self.reasons.append(f"Sideboard has {side_count}/15 cards")

    async def _fetch_card_data(self, session: aiohttp.ClientSession, card_name: str) -> Dict[str, Any]:
        """Fetch card data with rate limiting."""
        async with self._rate_limit_semaphore:
            await asyncio.sleep(self.SCRYFALL_DELAY)  # Respect rate limits
            try:
                url = f"https://api.scryfall.com/cards/named?fuzzy={card_name}"
                async with session.get(url, timeout=10) as response:
                    response.raise_for_status()
                    return await response.json()
            except Exception as e:
                self.reasons.append(f"Error checking {card_name}: {str(e)}")
                return {}

    async def _check_card(self, session: aiohttp.ClientSession, card_name: str, quantity: int) -> None:
        """Check legality of a single card."""
        card_data = await self._fetch_card_data(session, card_name)
        if not card_data:
            return

        # Check format legality
        if (legality := card_data.get('legalities', {}).get(self.format)) != "legal":
            status = legality.replace('_', ' ') if legality else "not found"
            self.reasons.append(f"{card_name} is {status} in {self.format}")

        # Check quantity limits
        if card_name in self.SPECIAL_LIMIT_CARDS:
            if quantity > self.SPECIAL_LIMIT_CARDS[card_name]:
                self.reasons.append(f"Too many {card_name} (max {self.SPECIAL_LIMIT_CARDS[card_name]})")
        elif (card_name not in self.UNLIMITED_CARDS 
              and not card_data.get('type_line', '').startswith('Basic')
              and quantity > 4):
            self.reasons.append(f"Too many {card_name} (max 4)")
            
    async def check_all_cards(self, session: aiohttp.ClientSession) -> None:
        """Check all cards with controlled concurrency."""
        tasks = []
        for card in self.deck.get("maindeck", []) + self.deck.get("sidedeck", []):
            tasks.append(self._check_card(session, card["cardname"], card["quantity"]))
        await asyncio.gather(*tasks)

    async def run_checks(self, session: aiohttp.ClientSession) -> str:
        """Execute all checks and return results."""
        await self.check_deck_size()
        await self.check_all_cards(session)
        return "\n".join(self.reasons) if self.reasons else f"Legal in {self.format}"


async def deck_check(deck: Dict[str, Any], deck_format: str, session: aiohttp.ClientSession = None) -> str:
    """Public async interface that accepts optional session."""
    async def _run_checks(session):
        checker = DeckChecker(deck, deck_format)
        return await checker.run_checks(session)
    
    if session:
        return await _run_checks(session)
    else:
        async with aiohttp.ClientSession() as new_session:
            return await _run_checks(new_session)


def sync_deck_check(deck: Dict[str, Any], deck_format: str) -> str:
    """Synchronous wrapper for compatibility."""
    return asyncio.run(deck_check(deck, deck_format))