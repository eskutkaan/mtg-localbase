import sqlite3
import tkinter as tk
from tkinter import ttk, scrolledtext
import threading
import io
import requests
from PIL import Image, ImageTk
import os
from functools import lru_cache

class MTGCardSearchApp:
    """
    A graphical application to search Magic: The Gathering cards in the database
    and display results with card images.
    """

    def __init__(self, root, db_path="mtg_cards.db"):
        """Initialize the search application."""
        self.root = root
        self.root.title("MTG Card Search")
        self.root.geometry("1200x800")
        self.db_path = db_path
        self.search_results = []
        self.image_cache_dir = "mtg_image_cache"

        # Create image cache directory if it doesn't exist
        if not os.path.exists(self.image_cache_dir):
            os.makedirs(self.image_cache_dir)

        # Create UI first, so we have status_var available for error messages
        self.create_widgets()

        # Set up the database connection
        self.connect_db()

    def connect_db(self):
        """Connect to the SQLite database."""
        try:
            self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self.cursor = self.conn.cursor()
            self.status_var.set(f"Connected to database: {self.db_path}")
            print(f"Connected to database: {self.db_path}")
        except sqlite3.Error as e:
            error_msg = f"Error connecting to database: {e}"
            self.status_var.set(error_msg)
            print(error_msg)

    def create_widgets(self):
        """Create and arrange UI components."""
        # Main frame
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Search frame
        search_frame = ttk.Frame(main_frame)
        search_frame.pack(fill=tk.X, pady=(0, 10))

        # Search label
        search_label = ttk.Label(search_frame, text="Search Cards:")
        search_label.pack(side=tk.LEFT, padx=(0, 5))

        # Search entry
        self.search_var = tk.StringVar()
        self.search_entry = ttk.Entry(search_frame, textvariable=self.search_var, width=50)
        self.search_entry.pack(side=tk.LEFT, padx=(0, 5))
        self.search_entry.bind("<Return>", self.on_search)

        # Search button
        search_button = ttk.Button(search_frame, text="Search", command=self.on_search)
        search_button.pack(side=tk.LEFT)

        # Advanced search options frame (expandable)
        self.create_advanced_search_frame(main_frame)

        # Results frame
        results_frame = ttk.LabelFrame(main_frame, text="Search Results")
        results_frame.pack(fill=tk.BOTH, expand=True)

        # Status bar (created early so it's available for error messages)
        self.status_var = tk.StringVar(value="Ready. Enter a search term to find cards.")
        status_bar = ttk.Label(self.root, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W)
        status_bar.pack(side=tk.BOTTOM, fill=tk.X)

        # Create a canvas with scrollbar for the results
        self.canvas = tk.Canvas(results_frame)
        scrollbar = ttk.Scrollbar(results_frame, orient=tk.VERTICAL, command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=scrollbar.set)

        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Frame inside canvas for results
        self.results_container = ttk.Frame(self.canvas)
        self.canvas_window = self.canvas.create_window((0, 0), window=self.results_container, anchor=tk.NW)

        # Configure canvas scrolling
        self.results_container.bind("<Configure>", self.on_frame_configure)
        self.canvas.bind("<Configure>", self.on_canvas_configure)

        # Mouse wheel scrolling
        self.canvas.bind_all("<MouseWheel>", self.on_mousewheel)

    def create_advanced_search_frame(self, parent):
        """Create the advanced search options frame."""
        # Advanced search toggle
        self.advanced_var = tk.BooleanVar(value=False)
        advanced_check = ttk.Checkbutton(
            parent,
            text="Advanced Search Options",
            variable=self.advanced_var,
            command=self.toggle_advanced_search
        )
        advanced_check.pack(anchor=tk.W, pady=(0, 5))

        # Advanced search frame (hidden initially)
        self.advanced_frame = ttk.Frame(parent)

        # Color filter
        color_frame = ttk.Frame(self.advanced_frame)
        color_frame.pack(fill=tk.X, pady=(0, 5))

        ttk.Label(color_frame, text="Colors:").pack(side=tk.LEFT, padx=(0, 5))

        self.white_var = tk.BooleanVar(value=False)
        self.blue_var = tk.BooleanVar(value=False)
        self.black_var = tk.BooleanVar(value=False)
        self.red_var = tk.BooleanVar(value=False)
        self.green_var = tk.BooleanVar(value=False)
        self.colorless_var = tk.BooleanVar(value=False)

        ttk.Checkbutton(color_frame, text="White", variable=self.white_var).pack(side=tk.LEFT)
        ttk.Checkbutton(color_frame, text="Blue", variable=self.blue_var).pack(side=tk.LEFT)
        ttk.Checkbutton(color_frame, text="Black", variable=self.black_var).pack(side=tk.LEFT)
        ttk.Checkbutton(color_frame, text="Red", variable=self.red_var).pack(side=tk.LEFT)
        ttk.Checkbutton(color_frame, text="Green", variable=self.green_var).pack(side=tk.LEFT)
        ttk.Checkbutton(color_frame, text="Colorless", variable=self.colorless_var).pack(side=tk.LEFT)

        # Type filter
        type_frame = ttk.Frame(self.advanced_frame)
        type_frame.pack(fill=tk.X, pady=(0, 5))

        ttk.Label(type_frame, text="Card Type:").pack(side=tk.LEFT, padx=(0, 5))

        self.type_var = tk.StringVar(value="Any")
        type_combo = ttk.Combobox(type_frame, textvariable=self.type_var, width=15)
        type_combo['values'] = ('Any', 'Creature', 'Instant', 'Sorcery', 'Artifact',
                               'Enchantment', 'Planeswalker', 'Land')
        type_combo.pack(side=tk.LEFT)

        # Rarity filter
        rarity_frame = ttk.Frame(self.advanced_frame)
        rarity_frame.pack(fill=tk.X, pady=(0, 5))

        ttk.Label(rarity_frame, text="Rarity:").pack(side=tk.LEFT, padx=(0, 5))

        self.rarity_var = tk.StringVar(value="Any")
        rarity_combo = ttk.Combobox(rarity_frame, textvariable=self.rarity_var, width=15)
        rarity_combo['values'] = ('Any', 'common', 'uncommon', 'rare', 'mythic')
        rarity_combo.pack(side=tk.LEFT)

    def toggle_advanced_search(self):
        """Show or hide the advanced search options."""
        if self.advanced_var.get():
            self.advanced_frame.pack(fill=tk.X, pady=(0, 10))
        else:
            self.advanced_frame.pack_forget()

    def on_frame_configure(self, event):
        """Reset the scroll region to encompass the inner frame."""
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def on_canvas_configure(self, event):
        """When the canvas changes size, resize the window within it."""
        width = event.width
        self.canvas.itemconfig(self.canvas_window, width=width)

    def on_mousewheel(self, event):
        """Handle mouse wheel scrolling."""
        self.canvas.yview_scroll(int(-1*(event.delta/120)), "units")

    def on_search(self, event=None):
        """Event handler for search button click or Enter key."""
        # Start the search in a separate thread
        threading.Thread(target=self.search_cards, daemon=True).start()

    def search_cards(self):
        """Search for cards based on the search criteria."""
        search_term = self.search_var.get().strip()

        # Update UI on main thread
        self.root.after(0, self.set_status, f"Searching for '{search_term}'...")

        if not search_term and not self.advanced_var.get():
            self.root.after(0, self.set_status, "Please enter a search term.")
            return

        # Clear previous results
        self.root.after(0, self.clear_results)

        # Build the query
        query = self.build_search_query(search_term)

        try:
            # Execute the query
            self.cursor.execute(query[0], query[1])
            results = self.cursor.fetchall()

            if not results:
                self.root.after(0, self.set_status, "No cards found matching your criteria.")
                return

            self.search_results = results
            self.root.after(0, self.display_results)

        except sqlite3.Error as e:
            error_msg = f"Database error: {e}"
            self.root.after(0, self.set_status, error_msg)

    def set_status(self, message):
        """Update the status bar text (safe to call from any thread)."""
        self.status_var.set(message)

    def clear_results(self):
        """Clear the results container (safe to call from any thread)."""
        for widget in self.results_container.winfo_children():
            widget.destroy()

    def build_search_query(self, search_term):
        """Build the SQL query based on search criteria."""
        query = "SELECT id, name, oracle_text, mana_cost, type_line, rarity, image_uri FROM cards WHERE 1=1"
        params = []

        # Add name search if provided
        if search_term:
            query += " AND (name LIKE ? OR oracle_text LIKE ?)"
            search_pattern = f"%{search_term}%"
            params.extend([search_pattern, search_pattern])

        # Add color filters if in advanced mode
        if self.advanced_var.get():
            color_conditions = []
            color_mapping = {
                'W': self.white_var.get(),
                'U': self.blue_var.get(),
                'B': self.black_var.get(),
                'R': self.red_var.get(),
                'G': self.green_var.get()
            }

            # Build color conditions
            for color, selected in color_mapping.items():
                if selected:
                    color_conditions.append(f"color_identity LIKE '%{color}%'")

            # Add colorless condition
            if self.colorless_var.get():
                color_conditions.append("color_identity = '[]'")

            # Combine color conditions if any are selected
            if color_conditions:
                query += f" AND ({' OR '.join(color_conditions)})"

            # Add type filter
            if self.type_var.get() != "Any":
                query += f" AND type_line LIKE '%{self.type_var.get()}%'"

            # Add rarity filter
            if self.rarity_var.get() != "Any":
                query += " AND rarity = ?"
                params.append(self.rarity_var.get())

        # Limit results and order by name
        query += " ORDER BY name LIMIT 10"

        return (query, params)

    def display_results(self):
        """Display the search results with card images."""
        # Update status
        self.set_status(f"Found {len(self.search_results)} cards.")

        # Clear previous results
        self.clear_results()

        # Display each card
        for i, card in enumerate(self.search_results):
            card_id, name, oracle_text, mana_cost, type_line, rarity, image_uri = card

            # Create a frame for this card
            card_frame = ttk.Frame(self.results_container)
            card_frame.pack(fill=tk.X, pady=10, padx=5)

            # Left side for image
            image_frame = ttk.Frame(card_frame, width=200)
            image_frame.pack(side=tk.LEFT, padx=(0, 10))

            # Create a placeholder for the image
            img_label = ttk.Label(image_frame, text="Loading image...")
            img_label.pack(padx=5, pady=5)

            # Right side for card details
            info_frame = ttk.Frame(card_frame)
            info_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

            # Card name with mana cost
            name_frame = ttk.Frame(info_frame)
            name_frame.pack(fill=tk.X)

            name_label = ttk.Label(name_frame, text=name, font=("", 12, "bold"))
            name_label.pack(side=tk.LEFT)

            if mana_cost:
                mana_label = ttk.Label(name_frame, text=f" — {mana_cost}")
                mana_label.pack(side=tk.LEFT)

            # Type line and rarity
            type_label = ttk.Label(info_frame, text=f"{type_line} ({rarity.capitalize()})")
            type_label.pack(anchor=tk.W)

            # Oracle text
            oracle_frame = ttk.Frame(info_frame)
            oracle_frame.pack(fill=tk.BOTH, expand=True, pady=(5, 0))

            oracle_text = oracle_text or "No text"
            text_area = scrolledtext.ScrolledText(oracle_frame, wrap=tk.WORD, height=5, width=50)
            text_area.insert(tk.END, oracle_text)
            text_area.config(state=tk.DISABLED)
            text_area.pack(fill=tk.BOTH, expand=True)

            # Add a separator unless it's the last card
            if i < len(self.search_results) - 1:
                ttk.Separator(self.results_container, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=5)

            # Load the image in a separate thread if available
            if image_uri:
                # Use thread with target that doesn't capture any free variables
                threading.Thread(
                    target=self.load_card_image,
                    args=(image_uri, card_id),
                    daemon=True
                ).start()

                # Store the image label reference to update it later
                # Use a tag in the label to store the card_id
                img_label.card_id = card_id

    def load_card_image(self, image_uri, card_id):
        """
        Load and display a card image.
        This function runs in a separate thread and doesn't use free variables.
        """
        image_path = os.path.join(self.image_cache_dir, f"{card_id}.jpg")
        error_message = None
        photo_image = None

        try:
            # Check if image is cached locally
            if os.path.exists(image_path):
                img = Image.open(image_path)
            else:
                # Download the image
                response = requests.get(image_uri, stream=True)
                if response.status_code == 200:
                    # Save to cache
                    img = Image.open(io.BytesIO(response.content))
                    img.save(image_path)
                else:
                    error_message = f"Image not available\n(Error {response.status_code})"
                    self.root.after(0, lambda: self.update_image_error(card_id, error_message))
                    return

            # Resize the image for display
            img = img.resize((200, int(200 * img.height / img.width)), Image.LANCZOS)
            photo_image = ImageTk.PhotoImage(img)

            # Schedule the update on the main thread
            self.root.after(0, lambda: self.update_image_success(card_id, photo_image))

        except Exception as e:
            error_message = f"Error loading image:\n{str(e)}"
            self.root.after(0, lambda: self.update_image_error(card_id, error_message))

    def update_image_success(self, card_id, photo):
        """Update image label with the loaded photo (called on main thread)."""
        # Find the label for this card_id
        for widget in self.results_container.winfo_children():
            for child in widget.winfo_children():
                for grandchild in child.winfo_children():
                    if hasattr(grandchild, 'card_id') and grandchild.card_id == card_id:
                        grandchild.config(image=photo)
                        # Store the photo reference in the label to prevent garbage collection
                        grandchild.image = photo
                        return

    def update_image_error(self, card_id, error_message):
        """Update image label with error message (called on main thread)."""
        # Find the label for this card_id
        for widget in self.results_container.winfo_children():
            for child in widget.winfo_children():
                for grandchild in child.winfo_children():
                    if hasattr(grandchild, 'card_id') and grandchild.card_id == card_id:
                        grandchild.config(text=error_message)
                        return

    def on_closing(self):
        """Clean up resources when closing the application."""
        if hasattr(self, 'conn') and self.conn:
            self.conn.close()
        self.root.destroy()

def main():
    """Main function to run the MTG card search application."""
    root = tk.Tk()
    app = MTGCardSearchApp(root)
    root.protocol("WM_DELETE_WINDOW", app.on_closing)
    root.mainloop()

if __name__ == "__main__":
    main()
