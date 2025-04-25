DROP PROCEDURE IF EXISTS upsert_contact(VARCHAR, VARCHAR, VARCHAR) CASCADE;
DROP PROCEDURE IF EXISTS insert_multiple_contacts_proc(contact_input[]) CASCADE;
DROP PROCEDURE IF EXISTS delete_contact_proc(TEXT, VARCHAR) CASCADE;
DROP FUNCTION IF EXISTS search_contacts(TEXT) CASCADE;
DROP FUNCTION IF EXISTS get_contacts_paginated(INT, INT) CASCADE;
DROP TYPE IF EXISTS contact_input CASCADE;

CREATE TABLE IF NOT EXISTS contacts (
    contact_id SERIAL PRIMARY KEY,
    first_name VARCHAR(100) NOT NULL,
    last_name VARCHAR(100) NOT NULL,
    phone_number VARCHAR(20) NOT NULL UNIQUE
);

CREATE TYPE contact_input AS (
    first_name VARCHAR(100),
    last_name VARCHAR(100),
    phone_number VARCHAR(20)
);

CREATE OR REPLACE FUNCTION search_contacts(p_pattern TEXT)
RETURNS TABLE(id INT, fname VARCHAR, lname VARCHAR, phone VARCHAR)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT c.contact_id, c.first_name, c.last_name, c.phone_number
    FROM contacts c
    WHERE p_pattern IS NULL OR p_pattern = ''
       OR c.first_name ILIKE ('%' || p_pattern || '%')
       OR c.last_name ILIKE ('%' || p_pattern || '%')
       OR c.phone_number LIKE ('%' || p_pattern || '%')
    ORDER BY c.last_name, c.first_name;
END;
$$;

CREATE OR REPLACE PROCEDURE upsert_contact(
    p_first_name VARCHAR,
    p_last_name VARCHAR,
    p_phone_number VARCHAR
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_contact_id INT;
BEGIN
    IF p_first_name IS NULL OR p_first_name = '' OR
       p_last_name IS NULL OR p_last_name = '' OR
       p_phone_number IS NULL OR p_phone_number = '' THEN
        RAISE EXCEPTION 'Input validation failed: First name, last name, and phone number cannot be empty.';
    END IF;

    SELECT contact_id INTO v_contact_id
    FROM contacts
    WHERE first_name = p_first_name AND last_name = p_last_name
    LIMIT 1;

    IF v_contact_id IS NOT NULL THEN
        IF EXISTS (SELECT 1 FROM contacts WHERE phone_number = p_phone_number AND contact_id != v_contact_id) THEN
             RAISE EXCEPTION 'Update failed: Phone number % already exists for a different contact.', p_phone_number;
        ELSE
            UPDATE contacts
            SET phone_number = p_phone_number
            WHERE contact_id = v_contact_id;
            RAISE NOTICE 'Updated phone number for existing contact % % (ID: %)', p_first_name, p_last_name, v_contact_id;
        END IF;
    ELSE
        BEGIN
            INSERT INTO contacts (first_name, last_name, phone_number)
            VALUES (p_first_name, p_last_name, p_phone_number);
             RAISE NOTICE 'Inserted new contact % %.', p_first_name, p_last_name;
        EXCEPTION
            WHEN unique_violation THEN
                RAISE EXCEPTION 'Insert failed: Phone number % already exists for another contact.', p_phone_number;
        END;
    END IF;
END;
$$;


CREATE OR REPLACE PROCEDURE insert_multiple_contacts_proc(
    p_contacts contact_input[]
)
LANGUAGE plpgsql
AS $$
DECLARE
    contact_rec contact_input;
    is_valid BOOLEAN;
    error_message TEXT;
    inserted_count INT := 0;
    failed_count INT := 0;
BEGIN
    RAISE NOTICE 'Starting bulk insert process for % contacts...', array_length(p_contacts, 1);

    FOREACH contact_rec IN ARRAY p_contacts
    LOOP
        is_valid := TRUE;
        error_message := NULL;

        IF contact_rec.first_name IS NULL OR contact_rec.first_name = '' THEN
            is_valid := FALSE; error_message := 'First name is empty.';
        ELSIF contact_rec.last_name IS NULL OR contact_rec.last_name = '' THEN
             is_valid := FALSE; error_message := 'Last name is empty.';
        ELSIF contact_rec.phone_number IS NULL OR contact_rec.phone_number = '' THEN
             is_valid := FALSE; error_message := 'Phone number is empty.';
        END IF;

        IF is_valid THEN
            BEGIN
                INSERT INTO contacts (first_name, last_name, phone_number)
                VALUES (contact_rec.first_name, contact_rec.last_name, contact_rec.phone_number);
                inserted_count := inserted_count + 1;
            EXCEPTION
                WHEN unique_violation THEN
                    RAISE NOTICE 'Skipped (duplicate phone): % %, Phone: %', contact_rec.first_name, contact_rec.last_name, contact_rec.phone_number;
                    failed_count := failed_count + 1;
                WHEN others THEN
                    RAISE WARNING 'Insert Error for % % (Phone: %): %', contact_rec.first_name, contact_rec.last_name, contact_rec.phone_number, SQLERRM;
                    failed_count := failed_count + 1;
            END;
        ELSE
             RAISE WARNING 'Skipped (invalid data): % %, Phone: %. Reason: %', contact_rec.first_name, contact_rec.last_name, contact_rec.phone_number, error_message;
             failed_count := failed_count + 1;
        END IF;
    END LOOP;

    RAISE NOTICE 'Bulk insert finished. Inserted: %, Failed/Skipped: %', inserted_count, failed_count;

END;
$$;

CREATE OR REPLACE FUNCTION get_contacts_paginated(p_limit INT, p_offset INT)
RETURNS TABLE(id INT, fname VARCHAR, lname VARCHAR, phone VARCHAR)
LANGUAGE plpgsql
AS $$
BEGIN
    IF p_limit <= 0 THEN
        p_limit := 10;
    END IF;
    IF p_offset < 0 THEN
        p_offset := 0;
    END IF;

    RETURN QUERY
    SELECT c.contact_id, c.first_name, c.last_name, c.phone_number
    FROM contacts c
    ORDER BY c.last_name, c.first_name
    LIMIT p_limit OFFSET p_offset;
END;
$$;

CREATE OR REPLACE PROCEDURE delete_contact_proc(
    p_identifier TEXT,
    p_type VARCHAR -- 'phone' or 'name'
)
LANGUAGE plpgsql
AS $$
DECLARE
    rows_deleted INT := 0;
    v_first_name VARCHAR;
    v_last_name VARCHAR;
    space_pos INT;
BEGIN
    IF p_identifier IS NULL OR p_identifier = '' OR p_type IS NULL OR p_type = '' THEN
       RAISE EXCEPTION 'Input validation failed: Identifier and type (phone/name) cannot be empty.';
    END IF;

    IF lower(p_type) = 'phone' THEN
        WITH deleted AS (
            DELETE FROM contacts WHERE phone_number = p_identifier RETURNING *
        )
        SELECT count(*) INTO rows_deleted FROM deleted;

    ELSIF lower(p_type) = 'name' THEN
        space_pos := position(' ' in p_identifier);
        IF space_pos = 0 THEN
             RAISE EXCEPTION 'Invalid name format for deletion. Expected "FirstName LastName".';
        END IF;
        v_first_name := trim(substring(p_identifier from 1 for space_pos - 1));
        v_last_name := trim(substring(p_identifier from space_pos + 1));

         IF v_first_name = '' OR v_last_name = '' THEN
              RAISE EXCEPTION 'Invalid name format for deletion. First or Last name missing.';
         END IF;

        WITH deleted AS (
            DELETE FROM contacts
            WHERE first_name = v_first_name AND last_name = v_last_name
            RETURNING *
        )
        SELECT count(*) INTO rows_deleted FROM deleted;
    ELSE
        RAISE EXCEPTION 'Invalid type specified for deletion. Use ''phone'' or ''name''.';
    END IF;

    IF rows_deleted > 0 THEN
        RAISE NOTICE 'Successfully deleted % contact(s) matching %: %', rows_deleted, p_type, p_identifier;
    ELSE
         RAISE NOTICE 'No contacts found matching %: %', p_type, p_identifier;
    END IF;

END;
$$;

COMMIT;