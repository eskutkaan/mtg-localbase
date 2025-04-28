import requests
import sqlite3
import time
import os
import json
from datetime import datetime

class MTGCardDatabase:
    """
    A class to manage a database of Magic: The Gathering cards.
    This script fetches data from the Scryfall API and stores it in a SQLite database.
    """

    def __init__(self, db_path="mtg_cards.db"):
        """Initialize the database connection and create tables if they don't exist."""
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path)
        self.cursor = self.conn.cursor()
        self.create_tables()
        self.api_base_url = "https://api.scryfall.com"

    def create_tables(self):
        """Create the necessary tables if they don't exist."""
        # Main cards table
        self.cursor.execute('''
        CREATE TABLE IF NOT EXISTS cards (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            oracle_text TEXT,
            mana_cost TEXT,
            cmc REAL,
            type_line TEXT,
            power TEXT,
            toughness TEXT,
            loyalty TEXT,
            colors TEXT,
            color_identity TEXT,
            set_code TEXT,
            set_name TEXT,
            rarity TEXT,
            artist TEXT,
            released_at TEXT,
            image_uri TEXT,
            scryfall_uri TEXT,
            price_usd REAL,
            price_eur REAL,
            price_tix REAL,
            last_updated TEXT
        )
        ''')

        # Table for card legalities in different formats
        self.cursor.execute('''
        CREATE TABLE IF NOT EXISTS legalities (
            card_id TEXT,
            format TEXT,
            status TEXT,
            PRIMARY KEY (card_id, format),
            FOREIGN KEY (card_id) REFERENCES cards(id)
        )
        ''')

        # Table for card keywords
        self.cursor.execute('''
        CREATE TABLE IF NOT EXISTS keywords (
            card_id TEXT,
            keyword TEXT,
            PRIMARY KEY (card_id, keyword),
            FOREIGN KEY (card_id) REFERENCES cards(id)
        )
        ''')

        self.conn.commit()

    def fetch_all_cards(self, update_existing=True):
        """
        Fetch all MTG cards from the Scryfall API and store them in the database.

        Args:
            update_existing (bool): If True, update existing cards in the database.
                                   If False, only add new cards.
        """
        print("Starting to fetch cards from Scryfall API...")

        # Get the first page of cards
        url = f"{self.api_base_url}/cards"
        response = requests.get(url)

        if response.status_code != 200:
            print(f"Error fetching cards: {response.status_code}")
            return

        data = response.json()
        total_cards = data.get('total_cards', 0)
        cards_processed = 0

        print(f"Found {total_cards} cards in total. Starting to process...")

        # Process the first page
        self.process_card_page(data['data'], update_existing)
        cards_processed += len(data['data'])
        print(f"Processed {cards_processed}/{total_cards} cards...")

        # Process all subsequent pages
        while data.get('has_more', False):
            # Be nice to the API by adding a small delay
            time.sleep(0.1)

            # Get the next page URL and fetch it
            next_page_url = data['next_page']
            response = requests.get(next_page_url)

            if response.status_code != 200:
                print(f"Error fetching page: {response.status_code}")
                break

            data = response.json()
            self.process_card_page(data['data'], update_existing)
            cards_processed += len(data['data'])
            print(f"Processed {cards_processed}/{total_cards} cards...")

        print("Finished fetching all cards!")

    def update_database(self):
        """
        Update the database with new cards since the last update.
        Uses the Scryfall API's /cards/search endpoint with a date filter.
        """
        # Get the date of the last update
        self.cursor.execute("SELECT MAX(released_at) FROM cards")
        result = self.cursor.fetchone()
        last_update_date = result[0] if result[0] else "2000-01-01"  # Default old date if no data

        print(f"Updating database with cards released after {last_update_date}...")

        # Format query for Scryfall's search
        search_query = f"date>{last_update_date}"
        url = f"{self.api_base_url}/cards/search?q={search_query}"

        try:
            response = requests.get(url)

            # If no new cards, the API will return 404
            if response.status_code == 404:
                print("No new cards found since the last update.")
                return

            if response.status_code != 200:
                print(f"Error fetching updates: {response.status_code}")
                return

            data = response.json()
            total_new_cards = data.get('total_cards', 0)
            cards_processed = 0

            print(f"Found {total_new_cards} new cards. Starting to process...")

            # Process the first page
            self.process_card_page(data['data'], update_existing=True)
            cards_processed += len(data['data'])
            print(f"Processed {cards_processed}/{total_new_cards} new cards...")

            # Process all subsequent pages
            while data.get('has_more', False):
                time.sleep(0.1)
                next_page_url = data['next_page']
                response = requests.get(next_page_url)

                if response.status_code != 200:
                    print(f"Error fetching page: {response.status_code}")
                    break

                data = response.json()
                self.process_card_page(data['data'], update_existing=True)
                cards_processed += len(data['data'])
                print(f"Processed {cards_processed}/{total_new_cards} new cards...")

            print("Database update complete!")

        except Exception as e:
            print(f"Error during update: {e}")

    def process_card_page(self, cards, update_existing=True):
        """
        Process a page of cards from the API response.

        Args:
            cards (list): List of card objects from the API
            update_existing (bool): Whether to update existing cards
        """
        for card in cards:
            # Skip cards with no Oracle text (like art cards) if you prefer
            # if not card.get('oracle_text'):
            #    continue

            # Skip digital-only cards (like those on MTG Arena) if you prefer
            # if card.get('digital', False):
            #    continue

            card_id = card['id']

            # Check if the card already exists
            self.cursor.execute("SELECT id FROM cards WHERE id = ?", (card_id,))
            existing_card = self.cursor.fetchone()

            if existing_card and not update_existing:
                continue  # Skip existing cards if not updating

            # Handle double-faced cards and card faces
            oracle_text = card.get('oracle_text', '')
            if 'card_faces' in card and not oracle_text:
                # For double-faced cards, combine the text of both faces
                faces_text = []
                for face in card['card_faces']:
                    if 'oracle_text' in face:
                        faces_text.append(face['oracle_text'])
                oracle_text = " // ".join(faces_text)

            # Extract and format colors
            colors = json.dumps(card.get('colors', []))
            color_identity = json.dumps(card.get('color_identity', []))

            # Extract and format image URI
            image_uri = None
            if 'image_uris' in card and 'normal' in card['image_uris']:
                image_uri = card['image_uris']['normal']
            elif 'card_faces' in card and 'image_uris' in card['card_faces'][0]:
                image_uri = card['card_faces'][0]['image_uris'].get('normal', None)

            # Prepare data for insertion/update
            card_data = (
                card_id,
                card.get('name', ''),
                oracle_text,
                card.get('mana_cost', ''),
                card.get('cmc', 0.0),
                card.get('type_line', ''),
                card.get('power', ''),
                card.get('toughness', ''),
                card.get('loyalty', ''),
                colors,
                color_identity,
                card.get('set', ''),
                card.get('set_name', ''),
                card.get('rarity', ''),
                card.get('artist', ''),
                card.get('released_at', ''),
                image_uri,
                card.get('scryfall_uri', ''),
                card.get('prices', {}).get('usd', None),
                card.get('prices', {}).get('eur', None),
                card.get('prices', {}).get('tix', None),
                datetime.now().isoformat()
            )

            if existing_card:
                # Update existing card
                self.cursor.execute('''
                UPDATE cards SET
                    name = ?, oracle_text = ?, mana_cost = ?, cmc = ?,
                    type_line = ?, power = ?, toughness = ?, loyalty = ?,
                    colors = ?, color_identity = ?, set_code = ?, set_name = ?,
                    rarity = ?, artist = ?, released_at = ?, image_uri = ?,
                    scryfall_uri = ?, price_usd = ?, price_eur = ?, price_tix = ?,
                    last_updated = ?
                WHERE id = ?
                ''', card_data[1:] + (card_id,))

                # Delete existing legalities and keywords to recreate them
                self.cursor.execute("DELETE FROM legalities WHERE card_id = ?", (card_id,))
                self.cursor.execute("DELETE FROM keywords WHERE card_id = ?", (card_id,))
            else:
                # Insert new card
                self.cursor.execute('''
                INSERT INTO cards (
                    id, name, oracle_text, mana_cost, cmc, type_line, power,
                    toughness, loyalty, colors, color_identity, set_code,
                    set_name, rarity, artist, released_at, image_uri, scryfall_uri,
                    price_usd, price_eur, price_tix, last_updated
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', card_data)

            # Add legalities
            if 'legalities' in card:
                for format_name, status in card['legalities'].items():
                    self.cursor.execute('''
                    INSERT INTO legalities (card_id, format, status)
                    VALUES (?, ?, ?)
                    ''', (card_id, format_name, status))

            # Add keywords
            if 'keywords' in card and card['keywords']:
                for keyword in card['keywords']:
                    self.cursor.execute('''
                    INSERT INTO keywords (card_id, keyword)
                    VALUES (?, ?)
                    ''', (card_id, keyword))

        self.conn.commit()

    def search_cards(self, query, limit=20):
        """
        Search for cards in the database.

        Args:
            query (str): The search query
            limit (int): Maximum number of results to return

        Returns:
            list: List of matching card dictionaries
        """
        search_pattern = f"%{query}%"
        self.cursor.execute('''
        SELECT id, name, oracle_text, mana_cost, type_line
        FROM cards
        WHERE name LIKE ? OR oracle_text LIKE ? OR type_line LIKE ?
        LIMIT ?
        ''', (search_pattern, search_pattern, search_pattern, limit))

        results = []
        for row in self.cursor.fetchall():
            results.append({
                'id': row[0],
                'name': row[1],
                'oracle_text': row[2],
                'mana_cost': row[3],
                'type_line': row[4]
            })

        return results

    def get_card_details(self, card_id):
        """
        Get detailed information about a specific card.

        Args:
            card_id (str): The card's ID

        Returns:
            dict: Card details including legalities and keywords
        """
        # Get basic card info
        self.cursor.execute('''
        SELECT * FROM cards WHERE id = ?
        ''', (card_id,))

        columns = [desc[0] for desc in self.cursor.description]
        card_data = self.cursor.fetchone()

        if not card_data:
            return None

        # Convert to dictionary
        card_dict = dict(zip(columns, card_data))

        # Convert JSON strings back to lists
        card_dict['colors'] = json.loads(card_dict['colors'])
        card_dict['color_identity'] = json.loads(card_dict['color_identity'])

        # Get legalities
        self.cursor.execute('''
        SELECT format, status FROM legalities WHERE card_id = ?
        ''', (card_id,))

        card_dict['legalities'] = {}
        for row in self.cursor.fetchall():
            card_dict['legalities'][row[0]] = row[1]

        # Get keywords
        self.cursor.execute('''
        SELECT keyword FROM keywords WHERE card_id = ?
        ''', (card_id,))

        card_dict['keywords'] = [row[0] for row in self.cursor.fetchall()]

        return card_dict

    def get_stats(self):
        """
        Get database statistics.

        Returns:
            dict: Statistics about the database
        """
        stats = {}

        # Get total card count
        self.cursor.execute("SELECT COUNT(*) FROM cards")
        stats['total_cards'] = self.cursor.fetchone()[0]

        # Get card count by color identity
        self.cursor.execute("""
        SELECT
            CASE
                WHEN color_identity = '[]' THEN 'Colorless'
                WHEN color_identity = '["W"]' THEN 'White'
                WHEN color_identity = '["U"]' THEN 'Blue'
                WHEN color_identity = '["B"]' THEN 'Black'
                WHEN color_identity = '["R"]' THEN 'Red'
                WHEN color_identity = '["G"]' THEN 'Green'
                ELSE 'Multicolor'
            END as color_group,
            COUNT(*) as count
        FROM cards
        GROUP BY color_group
        ORDER BY count DESC
        """)
        stats['colors'] = dict(self.cursor.fetchall())

        # Get card count by type
        self.cursor.execute("""
        SELECT
            CASE
                WHEN type_line LIKE '%Creature%' THEN 'Creature'
                WHEN type_line LIKE '%Planeswalker%' THEN 'Planeswalker'
                WHEN type_line LIKE '%Instant%' THEN 'Instant'
                WHEN type_line LIKE '%Sorcery%' THEN 'Sorcery'
                WHEN type_line LIKE '%Enchantment%' THEN 'Enchantment'
                WHEN type_line LIKE '%Artifact%' THEN 'Artifact'
                WHEN type_line LIKE '%Land%' THEN 'Land'
                ELSE 'Other'
            END as type_group,
            COUNT(*) as count
        FROM cards
        GROUP BY type_group
        ORDER BY count DESC
        """)
        stats['types'] = dict(self.cursor.fetchall())

        # Get last update time
        self.cursor.execute("SELECT MAX(last_updated) FROM cards")
        stats['last_updated'] = self.cursor.fetchone()[0]

        return stats

    def close(self):
        """Close the database connection."""
        self.conn.close()

def main():
    """Main function to demonstrate usage."""
    db = MTGCardDatabase()

    # Check if database file already exists and has data
    if os.path.exists(db.db_path) and os.path.getsize(db.db_path) > 0:
        print("Database already exists. Checking for updates...")
        db.update_database()
    else:
        print("Creating new database and fetching all cards...")
        db.fetch_all_cards()

    # Print some stats
    stats = db.get_stats()
    print("\nDatabase Statistics:")
    print(f"Total cards: {stats['total_cards']}")
    print(f"Last updated: {stats['last_updated']}")
    print("\nCard colors distribution:")
    for color, count in stats['colors'].items():
        print(f"  {color}: {count}")

    print("\nCard types distribution:")
    for type_name, count in stats['types'].items():
        print(f"  {type_name}: {count}")

    # Example search
    search_term = "dragon"
    print(f"\nSearching for '{search_term}':")
    results = db.search_cards(search_term, limit=5)
    for card in results:
        print(f"  {card['name']} - {card['type_line']}")

    # Close the connection
    db.close()

if __name__ == "__main__":
    main()
