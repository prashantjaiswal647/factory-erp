from sqlalchemy import create_engine, text

conn_str = "postgresql://postgres:postgres@localhost:5432/postgres"
try:
    engine = create_engine(conn_str)
    with engine.connect() as conn:
        print("SUCCESS connection to default postgres db!")
        res = conn.execute(text("SELECT datname FROM pg_database WHERE datistemplate = false"))
        print("Databases on this server:")
        for row in res:
            print(f"  {row[0]}")
except Exception as e:
    print(f"Failed to connect: {e}")
