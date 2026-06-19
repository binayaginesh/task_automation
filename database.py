import sqlite3

DATABASE_NAME = "mars_coordinates.db"


def get_connection():
    return sqlite3.connect(DATABASE_NAME)


def init_database():
    """
    Creates the database and table if they don't already exist.
    """

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS mars_coordinates (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            discord_id TEXT NOT NULL,

            username TEXT NOT NULL,

            url_x REAL NOT NULL,

            url_y REAL NOT NULL,

            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

            UNIQUE(url_x, url_y)

        );
    """)

    conn.commit()
    conn.close()


def coordinate_exists(url_x: float, url_y: float) -> bool:
    """
    Returns True if the exact X and Y coordinates already exist.
    """

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT 1
        FROM mars_coordinates
        WHERE url_x = ?
        AND url_y = ?
        LIMIT 1
    """, (url_x, url_y))

    exists = cursor.fetchone() is not None

    conn.close()

    return exists


def save_coordinate(
    discord_id: str,
    username: str,
    url_x: float,
    url_y: float
):
    """
    Saves a newly approved coordinate.
    """

    conn = get_connection()
    cursor = conn.cursor()

    try:

        cursor.execute("""
            INSERT INTO mars_coordinates
            (
                discord_id,
                username,
                url_x,
                url_y
            )
            VALUES
            (?, ?, ?, ?)
        """, (
            discord_id,
            username,
            url_x,
            url_y
        ))

        conn.commit()

    except sqlite3.IntegrityError:
        # Duplicate coordinate (UNIQUE constraint)
        pass

    finally:
        conn.close()


def print_database():
    """
    Prints every stored coordinate.
    Useful while testing.
    """

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            discord_id,
            username,
            url_x,
            url_y,
            created_at
        FROM mars_coordinates
    """)

    rows = cursor.fetchall()

    print("\n========== DATABASE ==========")

    for row in rows:
        print(row)

    print("==============================\n")

    conn.close()


# Create database automatically
init_database()