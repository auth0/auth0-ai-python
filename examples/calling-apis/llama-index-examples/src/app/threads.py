import uuid

threads = {}


def create_thread(user_id: str):
    if user_id not in threads:
        threads[user_id] = {}
    thread_id = str(uuid.uuid4())
    threads[user_id][thread_id] = {"interrupt": None}
    return thread_id


def get_thread(user_id: str, thread_id: str):
    return threads.get(user_id, {}).get(thread_id, None)
