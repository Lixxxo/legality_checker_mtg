import aiohttp
import asyncio
from PIL import Image
from io import BytesIO
from pathlib import Path
from typing import Dict, Tuple, Any


PPI = 300
MTG_CARD_SIZE = (int(2.5 * PPI), int(3.5 * PPI))
BASE_DIR = Path("Decks")

async def fetch_image(session: aiohttp.ClientSession, url: str) -> Image.Image:
    async with session.get(url) as response:
        return Image.open(BytesIO(await response.read()))

async def fetch_card_data(session: aiohttp.ClientSession, card_name: str) -> Dict[str, Any]:
    url = f"https://api.scryfall.com/cards/named?fuzzy={card_name}"
    async with session.get(url) as response:
        return await response.json()

async def plot_deck_async(
    deck: Dict[str, Any],
    basic: bool,
    dimensions: Tuple[int, int],
    deck_path: str,
    gap: int = 0
) -> Tuple[str, float]:
    deck_name = Path(deck_path).stem
    output_dir = BASE_DIR / deck_name
    output_dir.mkdir(parents=True, exist_ok=True)

    width, height = dimensions
    
    cards_per_row = (width - 100) // (MTG_CARD_SIZE[0] + gap)
    cards_per_col = (height - 100) // (MTG_CARD_SIZE[1] + gap)

    max_cards = cards_per_row * cards_per_col

    canvas = Image.new('RGBA', (width, height), (255, 255, 255, 255))
    card_count = 0
    page_count = 1
    deck_price = 0.0

    async with aiohttp.ClientSession() as session:
        for card in deck['maindeck'] + deck['sidedeck']:
            card_name, quantity = card["cardname"], card["quantity"]
            response = await fetch_card_data(session, card_name)
            
            if price := response.get('prices', {}).get('usd'):
                deck_price += float(price) * quantity

            if not basic and 'Basic Land' in response.get('type_line', ''):
                continue

            card_faces = []
            if 'image_uris' not in response:
                card_faces.extend(face['image_uris']['large'] for face in response.get('card_faces', []))
            else:
                card_faces.append(response['image_uris']['large'])
            print(f"card_name: {card_name}")
            print(f"price: ${price}, quantity: {quantity}")
            print(f"total: ${price*quantity}")
            print("---------------------------")
            for img in await asyncio.gather(*[fetch_image(session, url) for url in card_faces]):
                for _ in range(quantity):
                    
                    x = 50 + (card_count // cards_per_row) * (MTG_CARD_SIZE[0] + gap)
                    y = 50 + (card_count % cards_per_row) * (MTG_CARD_SIZE[1] + gap)
                    canvas.paste(img.resize(MTG_CARD_SIZE), (x, y))
                    card_count += 1
                    
                    if card_count == max_cards:
                        canvas.save(output_dir / f"{deck_name}_{page_count}.png")
                        print(f"Saved image as {deck_name}_{page_count}.png")
                        page_count += 1
                        card_count = 0
                        canvas = Image.new('RGBA', (width, height), (255, 255, 255, 255))
                        
        print("---------------------------")
        print(f"deck_price: ${deck_price}")
            
    if card_count > 1:
        canvas.save(output_dir / f"{deck_name}_{page_count}.png")

    return f"Deck saved to {output_dir}", round(deck_price, 2)