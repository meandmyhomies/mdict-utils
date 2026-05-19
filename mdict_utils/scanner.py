import os, sys, time, re, json
import glob
import multiprocessing
from tqdm import tqdm
from .writer import pack_mdd_file, pack_mdx_txt, pack_mdx_db, pack_mdd_db

# Move the global total here so it lives with the callback
total = 0

def make_callback(fmt):
    """
    Creates a callback for updating byte/item counts.
    If fmt is empty, it returns a hyper-fast silent dummy callback for parallel workers.
    """
    if not fmt:
        # Fast, silent return for multiprocessing workers
        return lambda value: None

    def callback(value):
        global total
        total += value
        # Flush ensures it paints to terminal immediately
        print(fmt % total, end='', flush=True)
    return callback

def add_resource(resource, dictionary, keys, is_mdd, encoding, fmt):
    if is_mdd:
        if resource.endswith('.db'):
            d = pack_mdd_db(resource, callback=make_callback(fmt))
        else:
            d = pack_mdd_file(resource, callback=make_callback(fmt))
    else:
        if resource.endswith('.db'):
            d = pack_mdx_db(resource, encoding=encoding, callback=make_callback(fmt))
        else:
            d = pack_mdx_txt(resource, encoding=encoding, callback=make_callback(fmt), keys=keys)
    dictionary.extend(d)

def _process_chunk(chunk_args):
    """
    Worker function: processes a chunk of files.
    By chunking the files, we drastically reduce IPC socket overhead.
    """
    targets, keys, is_mdd, encoding = chunk_args
    local_dict = []

    for target in targets:
        # We pass an empty string '' for the `fmt` parameter.
        # This completely stops the terminal buffer from choking on millions of prints.
        add_resource(target, local_dict, keys, is_mdd, encoding, '')

    return len(targets), local_dict

def parallel_scan_and_add(targets, keys, is_mdd, encoding, worker_count):
    total_targets = len(targets)
    if total_targets == 0:
        return []

    print(f"\rDiscovered {total_targets} resource targets. Processing in parallel...", flush=True)

    # Calculate chunk size based on the capped worker count rather than total CPU cores
    chunk_size = max(1, total_targets // (worker_count * 4))
    chunks = [targets[i:i + chunk_size] for i in range(0, total_targets, chunk_size)]

    worker_args = [(chunk, keys, is_mdd, encoding) for chunk in chunks]

    final_dictionary = []

    try:
        from tqdm import tqdm
        has_tqdm = True
    except ImportError:
        has_tqdm = False

    # Bind the pool to the computed worker_count (capped for HDD, uncapped for SSD)
    with multiprocessing.Pool(processes=worker_count) as pool:
        if has_tqdm:
            with tqdm(total=total_targets, desc="Scanning", unit="file") as pbar:
                for processed_count, local_dict in pool.imap_unordered(_process_chunk, worker_args):
                    final_dictionary.extend(local_dict)
                    pbar.update(processed_count)
        else:
            processed = 0
            for processed_count, local_dict in pool.imap_unordered(_process_chunk, worker_args):
                final_dictionary.extend(local_dict)
                processed += processed_count
                progress = (processed / total_targets) * 100
                sys.stdout.write(f"\rScanning files: {progress:.1f}% ({processed}/{total_targets})")
                sys.stdout.flush()
            print()

    return final_dictionary