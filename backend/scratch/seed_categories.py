import psycopg2
import os
from dotenv import load_dotenv

def seed():
    load_dotenv()
    db_url = os.getenv("DATABASE_URL")
    print(f"Connecting to database...")
    conn = psycopg2.connect(db_url)
    cur = conn.cursor()

    categories = [
        ('Plastic', 0, 450),
        ('Bottles', 1, 150),
        ('Paper', 2, 270),
        ('Metal', 3, 280)
    ]

    for name, code, validated_count in categories:
        try:
            # Check if name or code exists
            cur.execute("SELECT category_id FROM categories WHERE class_name = %s OR class_code = %s;", (name, code))
            res = cur.fetchone()
            if res:
                print(f"Category '{name}' (code {code}) already exists, skipping.")
            else:
                cur.execute(
                    "INSERT INTO categories (class_name, class_code, validated_count) VALUES (%s, %s, %s);",
                    (name, code, validated_count)
                )
                print(f"Seeded category: {name} with code {code}")
        except Exception as e:
            print(f"Error seeding category {name}: {e}")
            conn.rollback()

    conn.commit()
    cur.close()
    conn.close()
    print("Database seeding check complete!")

if __name__ == "__main__":
    seed()
