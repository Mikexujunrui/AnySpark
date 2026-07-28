"""Dedicated thread pools for I/O and CPU-bound operations.

Separate pools prevent long-running I/O operations (Neo4j queries, file I/O,
LLM calls) from starving the default asyncio thread pool, which is shared
with internal asyncio operations.
"""

import os
from concurrent.futures import ThreadPoolExecutor

# Separate pools with different sizing strategies:
# - io_pool: file I/O, Neo4j sync queries (I/O bound, many workers)
# - llm_pool: LLM API calls (network bound, moderate workers)
# - cpu_pool: CPU-bound operations like text processing (few workers)

_IO_WORKERS = max(4, (os.cpu_count() or 4) * 2)
_LLM_WORKERS = max(4, (os.cpu_count() or 4))
_CPU_WORKERS = max(2, (os.cpu_count() or 4) // 2)

io_pool = ThreadPoolExecutor(
    max_workers=_IO_WORKERS,
    thread_name_prefix="io-worker",
)

llm_pool = ThreadPoolExecutor(
    max_workers=_LLM_WORKERS,
    thread_name_prefix="llm-worker",
)

cpu_pool = ThreadPoolExecutor(
    max_workers=_CPU_WORKERS,
    thread_name_prefix="cpu-worker",
)


def get_io_pool() -> ThreadPoolExecutor:
    return io_pool


def get_llm_pool() -> ThreadPoolExecutor:
    return llm_pool


def get_cpu_pool() -> ThreadPoolExecutor:
    return cpu_pool


def shutdown_pools():
    """Gracefully shut down all thread pools. Call at application exit."""
    for pool in (io_pool, llm_pool, cpu_pool):
        pool.shutdown(wait=True)
