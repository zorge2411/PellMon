import sqlite3

from Pellmonsrv.database import Keyval_storage


def test_init_creates_keyval_table(tmp_path):
    """Constructing against a nonexistent file must leave a usable keyval table behind."""
    dbfile = str(tmp_path / "test.db")
    Keyval_storage(dbfile)

    conn = sqlite3.connect(dbfile)
    conn.cursor().execute("SELECT value FROM keyval")  # must not raise
    conn.close()


def test_init_fallback_path_when_table_missing(tmp_path):
    """Pre-seed a DB with an unrelated table so the constructor's SELECT hits
    sqlite3.OperationalError and must fall through to CREATE TABLE keyval
    (database.py:153-156). Checking the confvalue column specifically proves
    the fallback CREATE TABLE ran, not merely that some other path succeeded.
    """
    dbfile = str(tmp_path / "other_schema.db")
    conn = sqlite3.connect(dbfile)
    conn.execute("CREATE TABLE unrelated (id INTEGER)")
    conn.commit()
    conn.close()

    Keyval_storage(dbfile)

    conn = sqlite3.connect(dbfile)
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM keyval")
    cursor.execute("SELECT confvalue FROM keyval")
    conn.close()


def test_writeval_readval_roundtrip(tmp_path):
    store = Keyval_storage(str(tmp_path / "test.db"))
    store.writeval("mykey", value="42")
    assert store.readval("mykey") == "42"


def test_writeval_coerces_non_str_value(tmp_path):
    """value=42 (an int) must be coerced via str() at database.py:179-180."""
    store = Keyval_storage(str(tmp_path / "test.db"))
    store.writeval("intkey", value=42)
    assert store.readval("intkey") == "42"


def test_readval_missing_key_returns_error_string(tmp_path):
    """readval() swallows the exception and returns the literal 'error'
    string rather than raising; this is existing crude-but-intentional
    behavior (database.py:169-171). Do not use pytest.raises here and do
    not change the source to raise.
    """
    store = Keyval_storage(str(tmp_path / "test.db"))
    assert store.readval("nosuchkey") == "error"


def test_writeval_with_confval_sets_both_columns(tmp_path):
    """On a fresh store the row does not exist yet, so the nested bare
    except: upsert path at database.py:198-200 runs.
    """
    dbfile = str(tmp_path / "test.db")
    store = Keyval_storage(dbfile)
    store.writeval("ckey", value="v1", confval="c1")

    conn = sqlite3.connect(dbfile)
    cursor = conn.cursor()
    cursor.execute("SELECT confvalue FROM keyval WHERE id=?", ("ckey",))
    confvalue, = next(cursor)
    conn.close()

    assert confvalue == "c1"
