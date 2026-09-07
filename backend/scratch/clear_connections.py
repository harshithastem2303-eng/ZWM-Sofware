import psycopg2

try:
    conn = psycopg2.connect('postgresql://postgres:subhash8296424069@127.0.0.1:5432/postgres')
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute("SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE pid != pg_backend_pid();")
    print("Terminated idle connections successfully!")
    cur.close()
    conn.close()
except Exception as e:
    print("Error terminating connections:", e)
