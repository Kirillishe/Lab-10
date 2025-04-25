import psycopg2
import csv
import os
import sys
from config import DB_SETTINGS, CSV_HEADER


def connect_db():
    conn = None
    try:
        conn = psycopg2.connect(**DB_SETTINGS)

        return conn
    except (Exception, psycopg2.DatabaseError) as error:
        print(f"Error connecting to database: {error}")
        return None

def print_query_results(results):
    if results:
        print("\n--- Results ---")
        print(f"{'ID':<5} {'First Name':<15} {'Last Name':<15} {'Phone Number':<20}")
        print("-" * 55)
        for row in results:
            print(f"{row[0]:<5} {row[1]:<15} {row[2]:<15} {row[3]:<20}")
        print("-" * 55)
        print(f"Found {len(results)} contact(s).")
    else:
        print("\nNo results to display.")


def add_contact():
    try:
        first_name = input("Enter first name: ").strip()
        last_name = input("Enter last name: ").strip()
        phone_number = input("Enter phone number: ").strip()

        if not first_name or not last_name or not phone_number:
            print("Error: First name, last name, and phone number cannot be empty.")
            return

        conn = connect_db()
        if not conn:
            return

        try:
            with conn, conn.cursor() as cur:
                cur.execute("CALL upsert_contact(%s, %s, %s);", (first_name, last_name, phone_number))
        except psycopg2.Error as e:
             print(f"Database error during upsert: {e}")
        finally:
            if conn:
                conn.close()

    except (KeyboardInterrupt, EOFError):
        print("\nAdd contact cancelled.")

def add_contacts_from_csv():
    try:
        file_path = input("Enter path to CSV file: ").strip()
        if not os.path.exists(file_path):
            print(f"Error: File not found at '{file_path}'")
            return

        contacts_to_add = []
        try:
            with open(file_path, mode='r', encoding='utf-8') as csvfile:
                reader = csv.reader(csvfile)
                try:
                    header = next(reader)
                    if len(header) < 3 or header[0].lower() != 'first_name' or header[1].lower() != 'last_name' or header[2].lower() != 'phone_number':
                         print(f"Warning: CSV header mismatch or incorrect format. Expected ~{CSV_HEADER}, got {header}.")
                except StopIteration:
                     print("Error: CSV file is empty or has no header.")
                     return

                for row_num, row in enumerate(reader, start=2):
                     if len(row) >= 3:
                         first, last, phone = [col.strip() for col in row[:3]]
                         if first or last or phone:
                             contacts_to_add.append((first, last, phone))
                         else:
                             print(f"Warning: Skipping row {row_num} in CSV - seems empty.")
                     else:
                         print(f"Warning: Skipping row {row_num} in CSV - needs at least 3 columns.")

        except Exception as e:
             print(f"Error reading CSV file '{file_path}': {e}")
             return

        if not contacts_to_add:
            print("No valid contacts parsed from CSV to import.")
            return

        conn = connect_db()
        if not conn:
            return

        print(f"\nAttempting to import {len(contacts_to_add)} contacts via DB procedure...")
        print("Failures/skips will be reported as DB Notices/Warnings.")
        try:
            with conn, conn.cursor() as cur:
                cur.execute("CALL insert_multiple_contacts_proc(%s);", (contacts_to_add,))

        except psycopg2.Error as e:
            print(f"\nDatabase error during bulk insert procedure call: {e}")
        finally:
            if conn:
                conn.close()

    except (KeyboardInterrupt, EOFError):
        print("\nOperation cancelled.")


def update_contact():
    print("\n--- Update Contact ---")
    print("Note: This function uses direct SQL for flexible updates.")

    try:
        phone_to_find = input("Enter the CURRENT phone number of the contact to update: ").strip()
        if not phone_to_find:
            print("Error: Current phone number cannot be empty.")
            return

        conn = connect_db()
        if not conn: return
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT 1 FROM contacts WHERE phone_number = %s", (phone_to_find,))
                if cur.fetchone() is None:
                    print(f"Error: No contact found with phone number '{phone_to_find}'.")
                    conn.close()
                    return
        except psycopg2.Error as e:
            print(f"Error checking contact existence: {e}")
            if conn: conn.close()
            return

        print("\nWhat do you want to update?")
        print(" 1. First Name")
        print(" 2. Last Name")
        print(" 3. Phone Number")
        choice = input("Enter choice (1-3): ").strip()

        column_to_update = ""
        if choice == '1': column_to_update = "first_name"
        elif choice == '2': column_to_update = "last_name"
        elif choice == '3': column_to_update = "phone_number"
        else:
            print("Invalid choice.")
            if conn: conn.close()
            return

        new_value = input(f"Enter the new value for {column_to_update}: ").strip()
        if not new_value:
            print("Error: The new value cannot be empty.")
            if conn: conn.close()
            return

        sql = f"UPDATE contacts SET {column_to_update} = %s WHERE phone_number = %s;"
        try:
            with conn, conn.cursor() as cur:
                cur.execute(sql, (new_value, phone_to_find))
                if cur.rowcount > 0:
                    print(f"Contact with original phone '{phone_to_find}' updated successfully.")
                    if column_to_update == 'phone_number':
                        print(f"Phone number changed to '{new_value}'.")
                else:
                    print(f"No contact found with phone number '{phone_to_find}' during update.")
        except psycopg2.IntegrityError as e:
             if "contacts_phone_number_key" in str(e) and column_to_update == 'phone_number':
                 print(f"Error: Cannot update phone number to '{new_value}', as it already exists.")
             else:
                  print(f"Database integrity error: {e}")
        except psycopg2.Error as error:
            print(f"Error updating contact: {error}")
        finally:
            if conn:
                conn.close()

    except (KeyboardInterrupt, EOFError):
        print("\nUpdate cancelled.")
        if 'conn' in locals() and conn and not conn.closed: conn.close()


def find_contacts():
    try:
        pattern = input("Enter search text (part of name or phone, leave empty for all): ").strip()
        conn = connect_db()
        if not conn: return
        results = []
        try:
            with conn, conn.cursor() as cur:
                cur.execute("SELECT * FROM search_contacts(%s);", (pattern,))
                results = cur.fetchall()
        except psycopg2.Error as error:
            print(f"Error searching contacts: {error}")
        finally:
            if conn: conn.close()
        print_query_results(results)
    except (KeyboardInterrupt, EOFError):
        print("\nSearch cancelled.")


def list_contacts_paginated():
    try:
        try:
            limit = int(input("How many contacts per page? (e.g., 5): ").strip())
            offset = int(input("Which record to start from? (e.g., 0 for first page): ").strip())
            if limit <= 0: limit = 5 # Default
            if offset < 0: offset = 0 # Default
        except ValueError:
            print("Error: Please enter valid numbers.")
            return

        conn = connect_db()
        if not conn: return
        results = []
        try:
            with conn, conn.cursor() as cur:
                cur.execute("SELECT * FROM get_contacts_paginated(%s, %s);", (limit, offset))
                results = cur.fetchall()
        except psycopg2.Error as error:
            print(f"Error listing contacts: {error}")
        finally:
            if conn: conn.close()

        if results:
             start_num = offset + 1
             end_num = offset + len(results)
             print(f"\n--- Showing Contacts {start_num} to {end_num} ---")
             print_query_results(results)
        else:
             print("\nNo contacts found for this page/range.")
    except (KeyboardInterrupt, EOFError):
        print("\nListing cancelled.")

def delete_contact():
    try:
        print("\n--- Delete Contact ---")
        identifier = input("Enter the phone number OR full name ('FirstName LastName') to delete: ").strip()
        if not identifier:
            print("Error: Identifier cannot be empty.")
            return

        delete_type = input("Is this a 'phone' or 'name'? ").strip().lower()
        if delete_type not in ['phone', 'name']:
            print("Error: Type must be 'phone' or 'name'.")
            return

        confirm_msg = f"Are you sure you want to delete by {delete_type} '{identifier}'?"
        if delete_type == 'name':
            confirm_msg += " (Warning: May delete multiple contacts if names match!)"
        confirm = input(f"{confirm_msg} (yes/no): ").strip().lower()

        if confirm != 'yes':
            print("Deletion cancelled.")
            return

        conn = connect_db()
        if not conn:
            return

        print("\nExecuting delete command. Check DB notices for outcome.")
        try:
            with conn, conn.cursor() as cur:
                cur.execute("CALL delete_contact_proc(%s, %s);", (identifier, delete_type))
        except psycopg2.Error as e:
            print(f"Database error during deletion: {e}")
        finally:
            if conn:
                conn.close()

    except (KeyboardInterrupt, EOFError):
        print("\nDeletion cancelled.")

def export_contacts_to_csv():
    try:
        file_path = input("Enter output CSV file path (e.g., contacts_export.csv): ").strip()
        if not file_path:
            print("Error: Output file path cannot be empty.")
            return
        if not file_path.lower().endswith('.csv'): file_path += '.csv'

        sql = "SELECT first_name, last_name, phone_number FROM contacts ORDER BY last_name, first_name;"
        conn = connect_db()
        if not conn: return

        try:
            with conn, conn.cursor() as cur:
                cur.execute(sql)
                rows = cur.fetchall()
                count = len(rows)
                if count == 0:
                    print("No contacts found to export.")
                    return
                with open(file_path, mode='w', encoding='utf-8', newline='') as f:
                    writer = csv.writer(f)
                    writer.writerow(CSV_HEADER)
                    writer.writerows(rows)
                print(f"Successfully exported {count} contacts to '{file_path}'.")
        except psycopg2.Error as e: print(f"Database error during export query: {e}")
        except IOError as e: print(f"Error writing to file '{file_path}': {e}")
        finally:
            if conn: conn.close()
    except (KeyboardInterrupt, EOFError): print("\nExport cancelled.")

def execute_sql_script():
    try:
        file_path = input("Enter path to the .sql script file: ").strip()
        if not os.path.exists(file_path):
            print(f"Error: SQL script file not found at '{file_path}'")
            return
        if not file_path.lower().endswith('.sql'):
            print(f"Warning: File '{file_path}' does not have a .sql extension.")

        confirm = input(f"Execute script '{os.path.basename(file_path)}'? (yes/no): ").strip().lower()
        if confirm != 'yes':
            print("SQL script execution cancelled.")
            return

        sql_script_content = ""
        try:
            with open(file_path, mode='r', encoding='utf-8') as f: sql_script_content = f.read()
            if not sql_script_content.strip():
                print("Error: SQL script file is empty.")
                return
            print(f"\nRead script. Attempting execution...")
        except (IOError, OSError) as e:
             print(f"Error reading SQL script file: {e}")
             return

        conn = connect_db()
        if not conn: return

        try:
            with conn, conn.cursor() as cur: cur.execute(sql_script_content)
            print(f"Successfully executed SQL script '{os.path.basename(file_path)}'.")
        except psycopg2.Error as e: print(f"\nDatabase error during SQL script execution: {e}")
        finally:
            if conn: conn.close()
    except (KeyboardInterrupt, EOFError): print("\nSQL script execution cancelled.")
    except Exception as e: print(f"An unexpected error occurred: {e}")


def print_menu():
    print("\n--- Simple PhoneBook Menu (Strict Procedures) ---")
    print(" 1. Add/Update Contact (Proc: upsert_contact)")
    print(" 2. Add Contacts from CSV File (Proc: insert_multiple_contacts_proc)")
    print(" 3. Update Contact Details (Direct SQL)")
    print(" 4. Find Contacts (Func: search_contacts)")
    print(" 5. List Contacts (Func: get_contacts_paginated)")
    print(" 6. Delete Contact (Proc: delete_contact_proc)")
    print(" 7. Export Contacts to CSV (Direct SQL)")
    print(" 8. Execute SQL Script File (.sql)")
    print(" 0. Exit")
    print("---------------------------------------------------")

def main():
    print("Checking database connection...")
    conn = connect_db()
    if conn:
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT 1 FROM pg_proc WHERE proname = 'upsert_contact';")
                if not cur.fetchone():
                     print("WARNING: Core database procedure 'upsert_contact' not found.")
                     print("Please run the setup SQL script ('phonebook_db_setup_strict_procs.sql').")
            print("Database connection successful.")
        except psycopg2.Error as e:
             print(f"Database check failed: {e}")
             print("Exiting.")
             sys.exit(1)
        finally:
             conn.close()
    else:
         print("Initial database connection failed. Exiting.")
         sys.exit(1)


    while True:
        print_menu()
        choice = input("Enter your choice: ").strip()

        if choice == '1': add_contact()
        elif choice == '2': add_contacts_from_csv()
        elif choice == '3': update_contact()
        elif choice == '4': find_contacts()
        elif choice == '5': list_contacts_paginated()
        elif choice == '6': delete_contact()
        elif choice == '7': export_contacts_to_csv()
        elif choice == '8': execute_sql_script()
        elif choice == '0':
            print("Exiting PhoneBook. Goodbye!")
            break
        else:
            print("Invalid choice. Please try again.")

if __name__ == '__main__':
    print("Welcome to the Simple PhoneBook1!")
    main()