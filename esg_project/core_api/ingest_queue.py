import queue
import threading
import traceback
from django.db import connection, close_old_connections
from .models import IngestionBatch, RawPayload

# Thread-safe in-memory sequential task queue
_ingest_queue = queue.Queue()
_worker_thread = None
_lock = threading.Lock()

def _worker_loop():
    """
    Background worker thread loop that pulls tasks and processes them sequentially.
    Sequential processing ensures memory spikes never concurrent!
    """
    from .parsers import parse_payload
    from .views import invalidate_esg_cache
    
    while True:
        try:
            # Blocks until an ingestion task is available
            task = _ingest_queue.get()
            if task is None:
                break
                
            raw_payload_id = task.get('raw_payload_id')
            batch_id = task.get('batch_id')
            
            print(f"[Queue Worker] Processing payload {raw_payload_id} for batch {batch_id}...")
            
            close_old_connections()
            try:
                # Update IngestionBatch status to PROCESSING
                if batch_id:
                    IngestionBatch.objects.filter(id=batch_id).update(status="PROCESSING")
                
                # Execute the heavy parser
                parse_stats = parse_payload(raw_payload_id)
                
                # Invalidate lists caches
                invalidate_esg_cache()
                
                print(f"[Queue Worker] Success processing payload {raw_payload_id}!")
            except Exception as pe:
                print(f"[Queue Worker] Failure processing payload {raw_payload_id}: {pe}")
                traceback.print_exc()
                
                if batch_id:
                    IngestionBatch.objects.filter(id=batch_id).update(
                        status="ERROR",
                        error_count=1
                    )
            finally:
                _ingest_queue.task_done()
                close_old_connections()
                
        except Exception as qe:
            print(f"[Queue Worker] Critical queue error: {qe}")
            traceback.print_exc()

def start_worker():
    """
    Starts the background worker thread if it hasn't been started yet.
    """
    global _worker_thread
    with _lock:
        if _worker_thread is None or not _worker_thread.is_alive():
            _worker_thread = threading.Thread(target=_worker_loop, daemon=True, name="ESGIngestQueueWorker")
            _worker_thread.start()
            print("[Queue Worker] Background ingestion queue thread started successfully!")

def enqueue_ingestion(raw_payload_id, batch_id=None):
    """
    Pushes an ingestion task onto the background queue.
    """
    # Guarantee worker is running
    start_worker()
    _ingest_queue.put({
        'raw_payload_id': raw_payload_id,
        'batch_id': batch_id
    })
    print(f"[Queue Worker] Enqueued raw payload {raw_payload_id} for batch {batch_id}.")
