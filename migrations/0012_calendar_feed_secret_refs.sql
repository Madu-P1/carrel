-- 0012_calendar_feed_secret_refs.sql
--
-- Calendar feed URLs are revocable secrets. Raw URLs move to a secret store
-- (macOS Keychain in the desktop app, fake/in-memory store in tests). SQLite
-- keeps only the masked display URL, the existing url_hash duplicate key, and
-- a secret reference used at sync time.

ALTER TABLE calendar_feeds ADD COLUMN keychain_ref TEXT;
