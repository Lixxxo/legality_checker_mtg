# main.py
from __future__ import annotations
import argparse
import asyncio
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Tuple

import aiohttp
from prettytable import PrettyTable

from checker import DeckChecker
from plotter import plot_deck_async


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description='Check the legality of a Magic: The Gathering deck using the Scryfall API'
    )
    parser.add_argument(
        '-l', '--list', type=str, required=True,
        help='The filename of the decklist to check'
    )
    parser.add_argument(
        '-f', '--format', type=str, default="modern",
        help='The format to check the deck against (e.g. standard, modern, pioneer)'
    )
    parser.add_argument(
        '-p', '--print', action='store_true', default=False,
        help='Print the decklist in a formatted way'
    )
    parser.add_argument(
        '-b', '--basic', action='store_true', default=False,
        help='Print the decklist with the basic lands'
    )
    return parser.parse_args()


async def fetch_card_data(session: aiohttp.ClientSession, card_name: str) -> Dict[str, Any]:
    """Fetch card data from the Scryfall API for a given card name.
    
    Args:
        session: The aiohttp session to use for the request.
        card_name: The name of the card to fetch data for.
    
    Returns:
        The JSON response containing the card data.
    
    Raises:
        aiohttp.ClientError: If there's an error with the HTTP request.
    """
    url = f"https://api.scryfall.com/cards/named?exact={card_name}"
    async with session.get(url) as response:
        response.raise_for_status()
        return await response.json()


async def fetch_all_cards(deck: Dict[str, List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    """Fetch card data for all cards in the deck concurrently.
    
    Args:
        deck: The deck dictionary containing maindeck and sidedeck information.
    
    Returns:
        A list of JSON responses containing the card data.
    """
    async with aiohttp.ClientSession() as session:
        tasks = [
            fetch_card_data(session, card['cardname']) 
            for card in deck["maindeck"] + deck["sidedeck"]
        ]
        return await asyncio.gather(*tasks)


@lru_cache(maxsize=1000)
def get_cached_card_data(card_name: str) -> Dict[str, Any]:
    """Fetch cached card data, using the cache to avoid repeated requests.
    
    Args:
        card_name: The name of the card to fetch data for.
    
    Returns:
        The JSON response containing the card data.
    """
    async def _fetch():
        async with aiohttp.ClientSession() as session:
            return await fetch_card_data(session, card_name)
    
    return asyncio.run(_fetch())


def deck_show(deck: Dict[str, List[Dict[str, Any]]], verbose: bool = True) -> None:
    """Print the deck list in a formatted table using PrettyTable.
    
    Args:
        deck: The deck dictionary containing maindeck and sidedeck information.
        verbose: Whether to print the deck list.
    """
    if not verbose:
        return

    main = PrettyTable(field_names=["Card", "Quantity"])
    side = PrettyTable(field_names=["Card", "Quantity"])

    print("|\t\tMAIN DECK\t\t|")
    for card in deck["maindeck"]:
        main.add_row([card["cardname"], card["quantity"]])
    print(main)

    print("|\t\tSIDE DECK\t\t|")
    for card in deck["sidedeck"]:
        side.add_row([card["cardname"], card["quantity"]])
    print(side)


def ask_dimensions() -> Tuple[int, int]:
    """Ask the user for paper size and return dimensions in pixels.
    
    Returns:
        A tuple containing the width and height in pixels.
    """
    paper_sizes = {
        "Letter": (21.6, 27.9),
        "A4": (21.0, 29.7),
        "Office": (21.6, 33.0),
        "Custom": (0, 0)
    }
    
    print(f"Choose a paper size: {list(paper_sizes.keys())}")
    choice = input().capitalize() if input().strip() else "Letter"  # Default to Letter
    if choice not in paper_sizes:
        print(f"Invalid choice '{choice}', defaulting to Letter")
        choice = "Letter"
    if choice == "Custom":
        width = float(input("Enter value for Custom Width (cm): "))
        height = float(input("Enter value for Custom Height (cm): "))
        paper_sizes["Custom"] = (width, height)
    
    width_cm, height_cm = paper_sizes[choice]
    ppi = 300
    width_px = int(width_cm * ppi / 2.54)
    height_px = int(height_cm * ppi / 2.54)
    
    return width_px, height_px


def read_deckfile(filename: str) -> Dict[str, List[Dict[str, Any]]]:
    """Read a deck file and return maindeck and sidedeck information.
    
    Args:
        filename: The name of the deck file to read.
    
    Returns:
        A dictionary containing maindeck and sidedeck information.
    
    Raises:
        FileNotFoundError: If the deck file doesn't exist.
    """
    path = Path(filename)
    if not path.exists():
        raise FileNotFoundError(f"Deck file {filename} not found")
    
    maindeck = []
    sidedeck = []
    sideboard = False

    with path.open(encoding="utf-8") as file:
        for line in file:
            line = line.strip()
            if not line:
                sideboard = True
                continue

            parts = line.split()
            quantity = int(parts[0])
            card_name = " ".join(parts[1:])
            
            if sideboard:
                sidedeck.append({"cardname": card_name, "quantity": quantity})
            else:
                maindeck.append({"cardname": card_name, "quantity": quantity})

    return {"maindeck": maindeck, "sidedeck": sidedeck}


async def async_main():
    args = parse_args()
    deck = read_deckfile(args.list)
    deck_show(deck)
    
    async with aiohttp.ClientSession() as session:
        
        checker = DeckChecker(deck, args.format)
        legality_result = await checker.run_checks(session)
        print(legality_result)

        if args.print:
            dimensions = ask_dimensions()

            result = await plot_deck_async(deck, args.basic, dimensions, args.list)
            print(result)

if __name__ == "__main__":
    asyncio.run(async_main())