
import psycopg2
import csv
import os
from config import DB_SETTINGS, CSV_HEADER

def connect():
    """ Connect to the PostgreSQL database server """
    conn = None
    try:
        print('Connecting to the PostgreSQL database...')
        conn = psycopg2.connect(**DB_SETTINGS)
        print("Connection successful.")
        return conn
    except (Exception, psycopg2.DatabaseError) as error:
        print(f"Error connecting to database: {error}")
        return None

def create_tables():
    """ Create the contacts table in the database """
    command = """
        CREATE TABLE IF NOT EXISTS contacts (
            contact_id SERIAL PRIMARY KEY,
            first_name VARCHAR(100) NOT NULL,
            last_name VARCHAR(100) NOT NULL,
            phone_number VARCHAR(20) NOT NULL UNIQUE
        )
    """
    conn = connect()
    if not conn:
        return

    try:
        with conn, conn.cursor() as cur:
            print("Creating table 'contacts' if it doesn't exist...")
            cur.execute(command)
            print("Table check/creation complete.")
    except (Exception, psycopg2.DatabaseError) as error:
        print(f"Error creating table: {error}")
    finally:
        if conn is not None:
            conn.close()

def insert_contact_from_console():
    """ Inserts a single contact from console input """
    try:
        first_name = input("Enter first name: ").strip()
        last_name = input("Enter last name: ").strip()
        phone_number = input("Enter phone number: ").strip()

        if not first_name or not last_name or not phone_number:
            print("All fields (first name, last name, phone number) are required.")
            return

        sql = """
            INSERT INTO contacts(first_name, last_name, phone_number)
            VALUES(%s, %s, %s) RETURNING contact_id;
        """
        conn = connect()
        if not conn:
            return

        contact_id = None
        try:
            with conn, conn.cursor() as cur:
                cur.execute(sql, (first_name, last_name, phone_number))
                contact_id = cur.fetchone()[0]
                print(f"Contact '{first_name} {last_name}' inserted successfully with ID: {contact_id}")
        except (Exception, psycopg2.DatabaseError) as error:
            print(f"Error inserting contact: {error}")
            conn.rollback()
        finally:
            if conn is not None:
                conn.close()

    except KeyboardInterrupt:
        print("\nInsertion cancelled.")
    except EOFError:
        print("\nInput stream ended unexpectedly.")


def insert_contacts_from_csv(file_path):
    """ Inserts multiple contacts from a CSV file """
    if not os.path.exists(file_path):
        print(f"Error: CSV file not found at '{file_path}'")
        return

    sql = """
        INSERT INTO contacts(first_name, last_name, phone_number)
        VALUES(%s, %s, %s);
    """
    conn = connect()
    if not conn:
        return

    inserted_count = 0
    failed_count = 0

    try:
        with conn, conn.cursor() as cur, open(file_path, mode='r', encoding='utf-8') as csvfile:
            reader = csv.reader(csvfile)
            header = next(reader)

            if header != CSV_HEADER:
                 print(f"Warning: CSV header mismatch. Expected {CSV_HEADER}, got {header}. Proceeding anyway.")

            print(f"Importing contacts from '{file_path}'...")
            for row_num, row in enumerate(reader, start=2):
                if len(row) != 3:
                    print(f"Skipping row {row_num}: Incorrect number of columns ({len(row)} instead of 3).")
                    failed_count += 1
                    continue

                first_name, last_name, phone_number = [col.strip() for col in row]

                if not first_name or not last_name or not phone_number:
                    print(f"Skipping row {row_num}: Contains empty required field(s).")
                    failed_count += 1
                    continue

                try:
                    cur.execute(sql, (first_name, last_name, phone_number))
                    inserted_count += 1
                except (Exception, psycopg2.DatabaseError) as error:
                    print(f"Failed to insert row {row_num} ({first_name} {last_name}): {error}")
                    failed_count += 1
                    conn.rollback()

        print(f"\nCSV Import Summary:")
        print(f" Successfully inserted: {inserted_count}")
        print(f" Failed/Skipped rows: {failed_count}")

    except (Exception, psycopg2.DatabaseError) as error:
        print(f"\nAn error occurred during CSV import: {error}")
    except FileNotFoundError:
         print(f"Error: File not found '{file_path}'") #
    finally:
        if conn is not None:
            conn.close()

def update_contact():
    """ Updates a contact's first name or phone number based on phone number """
    try:
        search_phone = input("Enter the CURRENT phone number of the contact to update: ").strip()
        if not search_phone:
            print("Search phone number cannot be empty.")
            return

        print("What do you want to update?")
        print(" 1. First Name")
        print(" 2. Last Name")
        print(" 3. Phone Number")
        choice = input("Enter choice (1-3): ").strip()

        if choice == '1':
            field_to_update = 'first_name'
            new_value = input(f"Enter new first name: ").strip()
        elif choice == '2':
             field_to_update = 'last_name'
             new_value = input(f"Enter new last name: ").strip()
        elif choice == '3':
            field_to_update = 'phone_number'
            new_value = input(f"Enter new phone number: ").strip()
        else:
            print("Invalid choice.")
            return

        if not new_value:
             print("New value cannot be empty.")
             return

        sql = f"""
            UPDATE contacts
            SET {field_to_update} = %s
            WHERE phone_number = %s;
        """

        conn = connect()
        if not conn:
            return

        updated_rows = 0
        try:
            with conn, conn.cursor() as cur:
                cur.execute(sql, (new_value, search_phone))
                updated_rows = cur.rowcount
                if updated_rows > 0:
                    print(f"Contact with phone '{search_phone}' updated successfully.")
                else:
                    print(f"No contact found with phone number '{search_phone}'.")
        except (Exception, psycopg2.DatabaseError) as error:
             print(f"Error updating contact: {error}")
             conn.rollback()
        finally:
            if conn is not None:
                conn.close()

    except KeyboardInterrupt:
        print("\nUpdate cancelled.")
    except EOFError:
        print("\nInput stream ended unexpectedly.")


def query_contacts():
    """ Queries contacts with various filters """
    try:
        print("\n--- Query Contacts ---")
        print("Filter options:")
        print(" 1. Show All")
        print(" 2. Filter by First Name (contains)")
        print(" 3. Filter by Last Name (contains)")
        print(" 4. Filter by Phone Number (exact match)")
        choice = input("Enter choice (1-4): ").strip()

        base_sql = "SELECT contact_id, first_name, last_name, phone_number FROM contacts"
        where_clause = ""
        params = None

        if choice == '1':

            sql = base_sql + " ORDER BY last_name, first_name;"
        elif choice == '2':
            search_term = input("Enter first name fragment to search for: ").strip()
            if not search_term:
                print("Search term cannot be empty.")
                return
            where_clause = " WHERE first_name ILIKE %s"
            params = (f'%{search_term}%',)
            sql = base_sql + where_clause + " ORDER BY last_name, first_name;"
        elif choice == '3':
            search_term = input("Enter last name fragment to search for: ").strip()
            if not search_term:
                print("Search term cannot be empty.")
                return
            where_clause = " WHERE last_name ILIKE %s"
            params = (f'%{search_term}%',)
            sql = base_sql + where_clause + " ORDER BY last_name, first_name;"
        elif choice == '4':
            search_term = input("Enter exact phone number to search for: ").strip()
            if not search_term:
                 print("Search term cannot be empty.")
                 return
            where_clause = " WHERE phone_number = %s"
            params = (search_term,)
            sql = base_sql + where_clause + ";"
        else:
            print("Invalid choice.")
            return

        conn = connect()
        if not conn:
            return

        try:
            with conn, conn.cursor() as cur:
                if params:
                    cur.execute(sql, params)
                else:
                    cur.execute(sql)

                results = cur.fetchall()

                if results:
                    print("\n--- Search Results ---")
                    print(f"{'ID':<5} {'First Name':<15} {'Last Name':<15} {'Phone Number':<20}")
                    print("-" * 55)
                    for row in results:
                        print(f"{row[0]:<5} {row[1]:<15} {row[2]:<15} {row[3]:<20}")
                    print("-" * 55)
                    print(f"Found {len(results)} contact(s).")
                else:
                    print("\nNo contacts found matching your criteria.")

        except (Exception, psycopg2.DatabaseError) as error:
            print(f"Error querying contacts: {error}")
        finally:
            if conn is not None:
                conn.close()

    except KeyboardInterrupt:
        print("\nQuery cancelled.")
    except EOFError:
        print("\nInput stream ended unexpectedly.")


def delete_contact():
    """ Deletes a contact based on their phone number """
    try:
        phone_number = input("Enter the phone number of the contact to delete: ").strip()
        if not phone_number:
            print("Phone number cannot be empty.")
            return

        confirm = input(f"Are you sure you want to delete the contact with phone '{phone_number}'? (yes/no): ").strip().lower()
        if confirm != 'yes':
            print("Deletion cancelled.")
            return

        sql = "DELETE FROM contacts WHERE phone_number = %s;"
        conn = connect()
        if not conn:
            return

        deleted_rows = 0
        try:
            with conn, conn.cursor() as cur:
                cur.execute(sql, (phone_number,))
                deleted_rows = cur.rowcount
                if deleted_rows > 0:
                    print(f"Contact with phone '{phone_number}' deleted successfully.")
                else:
                    print(f"No contact found with phone number '{phone_number}'.")
        except (Exception, psycopg2.DatabaseError) as error:
            print(f"Error deleting contact: {error}")
            conn.rollback()
        finally:
            if conn is not None:
                conn.close()

    except KeyboardInterrupt:
        print("\nDeletion cancelled.")
    except EOFError:
        print("\nInput stream ended unexpectedly.")


def print_menu():
    print("\n--- PhoneBook Menu ---")
    print("1. Add Contact (Console)")
    print("2. Add Contacts (from CSV)")
    print("3. Update Contact")
    print("4. Query Contacts")
    print("5. Delete Contact")
    print("6. Initialize/Create Table (Run once)")
    print("0. Exit")
    print("----------------------")

def main():
    while True:
        print_menu()
        choice = input("Enter your choice: ").strip()

        if choice == '1':
            insert_contact_from_console()
        elif choice == '2':
            csv_path = input("Enter the path to the CSV file: ").strip()
            insert_contacts_from_csv(csv_path)
        elif choice == '3':
            update_contact()
        elif choice == '4':
            query_contacts()
        elif choice == '5':
            delete_contact()
        elif choice == '6':
             create_tables()
        elif choice == '0':
            print("Exiting PhoneBook. Goodbye!")
            break
        else:
            print("Invalid choice. Please try again.")

if __name__ == '__main__':
    main()