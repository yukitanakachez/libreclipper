"""Locks shared by the web app's thread pool and the background worker."""

import threading

# Whoever reads, changes and rewrites a job's JSON state (candidates, word fixes, clips, settings) holds this.
WRITE_LOCK = threading.Lock()
