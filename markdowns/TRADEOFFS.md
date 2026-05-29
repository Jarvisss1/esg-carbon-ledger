# Strategic Engineering Trade-offs

When building a high-integrity carbon ledger within tight resource constraints, we had to make some tough, deliberate technical compromises. Our primary focus was absolute data integrity, bulletproof security, and auditable reproducibility, even if it meant skipping some conventional enterprise architecture patterns. 

Here are the key trade-offs we chose, why we made them, and how we handle their limitations:

---

## 1. Simple In-Memory Queue vs. Heavy Distributed Workers (Celery + Redis)

* **What we did**: We built a thread-safe, sequential background queue (`ESGIngestQueueWorker` using standard Python `queue.Queue`) that runs directly inside the Django web process.
* **Why we did it**: We needed to run the app comfortably within Render’s free-tier memory limit (512MB RAM). Introducing Celery and Redis would have blown past this budget instantly. Processing ingestion files sequentially also has a huge side-benefit: it completely prevents database row-locking contention and duplicate key race conditions during bulk uploads.
* **The compromise**: Since the queue lives in application memory, any server restart or sleep cycle will lose currently queued tasks. We accepted this risk because raw file uploads are saved as persistent `RawPayload` database rows *before* they are queued. If a server restart interrupts parsing, an analyst can simply click "Reprocess" in the dashboard to safely rerun the ingestion.

---

## 2. Schema-Free JSON Metadata vs. Dynamic SQL Schema Migrations

* **What we did**: We store operational analyst data (like audit logs and workflow assignments) directly inside a flexible, schema-free JSON column (`raw_data`) rather than running database schema migrations (`ALTER TABLE`).
* **Why we did it**: Running migrations on large transactional databases carries risks of row locking, table locking, and downtime. Storing extra metadata as JSON fields lets us extend and adjust our data models instantly without database friction.
* **The compromise**: We trade away strict, database-level SQL column validations. We compensate for this by running validations at the Django application/serializer layer and utilizing native JSON queries (`raw_data__assigned_to`) supported by PostgreSQL and SQLite to perform lightning-fast filters.

---

## 3. Local In-Memory Cache vs. Distributed Cache Cluster (Redis)

* **What we did**: We use Django's standard local memory caching (`LocMemCache`) to speed up read-heavy endpoints like dashboards, historical logs, and record drawers.
* **Why we did it**: Speed and simplicity. Local memory reads happen in under 1 millisecond and require zero network roundtrips or extra infrastructure costs.
* **The compromise**: If we scale the web app horizontally across multiple nodes, their local caches will fall out of sync since invalidations on one node won't automatically clean up the other nodes. For our current single-node deployment, this is a non-issue. We also execute immediate global cache flushes (`cache.clear()`) on any database write to guarantee the UI is always showing 100% fresh data.

---

## 4. Local File-Based Mock Emails vs. Live SendGrid / SMTP Relays

* **What we did**: We configured all email notifications and export attachments to use Django's local file-based email backend, saving generated emails into a local `sent_emails/` folder.
* **Why we did it**: Bulletproof security and ease of local testing. We don't have to manage sensitive SMTP passwords or SendGrid API credentials in development, and the platform is completely immune to network lag or external API rate limits during export stress tests.
* **The compromise**: The application doesn't deliver real emails to actual inboxes out-of-the-box. Instead, it provides developers and auditors with clear, raw text logs on disk to inspect exact headers and generated CSV attachments. Switching to a live production mail relay is as simple as updating a few environment variables in the settings config.