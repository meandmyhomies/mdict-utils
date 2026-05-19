from html import parser
import os.path
import argparse
import csv

from . import about
from . import reader
from .writer import pack, pack_mdd_file, pack_mdx_txt, pack_mdx_db, pack_mdd_db, \
    txt2db, db2txt
from .utils import ElapsedTimer
from .scanner import make_callback, add_resource, parallel_scan_and_add
import mdict_utils.scanner as scanner_module

def run():
    epilog = ''
    parser = argparse.ArgumentParser(prog='mdict', description=about.description, epilog=epilog)
    parser.add_argument('--version', action='version',
                        version='%%(prog)s version %s - written by %s <%s>' % (
                            about.version, about.author, about.email),
                        help='show version')
    parser.add_argument('-k', dest='key', action='store_true', help='show mdx/mdd keys')
    parser.add_argument('-m', dest='meta', action='store_true', help='show mdx/mdd meta information')
    parser.add_argument('-q', dest='query', metavar='<key>', help='query KEY from mdx/mdd')
    parser.add_argument('--txt-db', action='store_true', help='convert mdx txt to sqlite3 db. <mdx/mdd> is ".txt"')
    parser.add_argument('--db-txt', action='store_true', help='convert sqlite3 db to mdx txt. <mdx/mdd> is ".db"')
    parser.add_argument('mdict', metavar='<mdx/mdd>', help='Dictionary MDX/MDD file')

    group = parser.add_argument_group('Reader')
    group.add_argument('-x', dest='extract', action='store_true', help='extract mdx/mdd file.')
    group.add_argument('-d', dest='exdir', metavar='<exdir>', help='extract mdx/mdd to directory')
    group.add_argument('--exdb', action='store_true', help='extract mdx/mdd to DB')
    group.add_argument('--exdb-zip', action='store_true', help='extract mdx/mdd to DB with ZIP compress')
    group.add_argument('--split-n', metavar='<number>', help='split MDX TXT to N files')
    group.add_argument('--split-az', action='store_true', help='split MDX TXT to files by a...z')

    group = parser.add_argument_group('Writer')
    group.add_argument('-a', dest='add', metavar='<resource>', action='append', help='add resource file to mdx/mdd file')
    group.add_argument('--title', metavar='<title>', help='Dictionary title file')
    group.add_argument('--description', metavar='<description>', help='Dictionary descritpion file')
    group.add_argument('--encoding', metavar='<encoding>', default='utf-8', help='mdx txt file encoding')
    group.add_argument('--key-size', metavar='<size>', type=int, default=32, help='Key block size. unit: KB')
    group.add_argument('--record-size', metavar='<size>', type=int, default=64, help='Record block size. unit: KB')
    group.add_argument('--key-file', metavar='<key file>', help='only pack some keys in the file')

    group = parser.add_argument_group('Compact HTML')
    group.add_argument('--convert-chtml', action='store_true', help='convert compact html.')

    group = parser.add_argument_group('Performance Tuning')
    group.add_argument('--hdd-workers', type=int, default=2, help='Max parallel processes to use if an HDD is detected to prevent thrashing (default: 2)')

    args = parser.parse_args()

    global total

    if args.meta:
        with ElapsedTimer(verbose=True):
            meta = reader.meta(args.mdict)
            for k, v in meta.items():
                print('%s: "%s"' % (k.title(), v))
    elif args.key:
        keys = reader.get_keys(args.mdict)
        count = 0
        for key in keys:
            count += 1
            print(key)
    elif args.txt_db:
        with ElapsedTimer(verbose=True):
            total = 0
            fmt = '\rConvert "%s": %%s' % args.mdict
            txt2db(args.mdict, callback=make_callback(fmt))
            print()
    elif args.db_txt:
        with ElapsedTimer(verbose=True):
            total = 0
            fmt = '\rConvert "%s": %%s' % args.mdict
            db2txt(args.mdict, callback=make_callback(fmt))
            print()
    elif args.query:
        # fix dash prefix in shell enviroment
        # mdict -q "\-ment" xxxx.mdx
        query = args.query[1:] if args.query[0] == '\\' else args.query
        with ElapsedTimer(verbose=True):
            record = reader.query(args.mdict, query)
            print(record)
    elif args.extract:
        with ElapsedTimer(verbose=True):
            if args.exdb or args.exdb_zip:
                reader.unpack_to_db(args.exdir, args.mdict, zip=args.exdb_zip)
            else:
                if args.split_az:
                    split = 'az'
                elif args.split_n:
                    split = args.split_n
                else:
                    split = None
                reader.unpack(args.exdir, args.mdict, split=split, convert_chtml=args.convert_chtml)
    elif args.add:
        from .scanner import parallel_scan_and_add
        from ssd_checker import is_ssd
        import os
        import multiprocessing

        with ElapsedTimer(verbose=True):
            keys = []
            if args.key_file:
                with open(args.key_file, 'rt', newline='', encoding='utf-8') as f_csv:
                    csv_reader = csv.reader(f_csv)
                    for row in csv_reader:
                        keys.append(row[0])
            is_mdd = args.mdict.endswith('.mdd')

            target_files = []
            is_all_ssd = True

            for resource in args.add:
                # 1. Determine the path to check for SSD status
                if '*' in resource or '?' in resource or ('[' in resource and ']' in resource):
                    import glob
                    target_files.extend(glob.glob(resource))
                    # Extract the base directory of the glob to check the drive type
                    check_path = os.path.dirname(resource) or '.'
                else:
                    target_files.append(resource)
                    check_path = resource

                # 2. Check SSD status ONCE per -a argument using absolute path
                if not is_ssd(os.path.abspath(check_path)):
                    is_all_ssd = False

            # 3. Determine the worker limit
            cpu_cores = multiprocessing.cpu_count()
            if is_all_ssd:
                worker_count = cpu_cores
                print(f"SSD detected. Utilizing all {worker_count} cores for I/O.")
            else:
                worker_count = min(args.hdd_workers, cpu_cores)
                print(f"HDD detected. Capping parallel I/O to {worker_count} workers to prevent disk thrashing.")

            # Pass worker_count down to the parallel scanner
            dictionary = parallel_scan_and_add(target_files, keys, is_mdd, args.encoding, worker_count)

            print()
            title = ''
            description = ''
            if args.title:
                title = open(args.title, 'rt', encoding='utf-8').read().strip()
            if args.description:
                description = open(args.description, 'rt', encoding='utf-8').read().strip()
            print('Pack to "%s"' % args.mdict)
            pack(args.mdict, dictionary, title, description,
                 key_size=args.key_size * 1024, record_size=args.record_size * 1024,
                 encoding=args.encoding, is_mdd=is_mdd)
    else:
        parser.print_help()


if __name__ == '__main__':
    run()
