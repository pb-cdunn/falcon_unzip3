
from falcon_kit.multiproc import Pool
import falcon_kit.util.io as io
import argparse
import sys
import glob
import os
from heapq import heappush, heappop, heappushpop

Reader = io.CapturedProcessReaderContext


def get_rid_to_ctg(fn):
    rid_to_ctg = {}
    with open(fn) as f:
        for row in f:
            row = row.strip().split()
            pid, rid, oid, ctg = row
            rid_to_ctg.setdefault(rid, set())
            rid_to_ctg[rid].add(ctg)
    return rid_to_ctg


def run_tr_stage1(db_fn, fn, min_len, bestn, rid_to_ctg):
    cmd = "LA4Falcon -m %s %s" % (db_fn, fn)
    reader = Reader(cmd)
    with reader:
        return fn, tr_stage1(reader.readlines, min_len, bestn, rid_to_ctg)


def tr_stage1(readlines, min_len, bestn, rid_to_ctg):
    """
    for each read in the b-read column inside the LAS files, we
    keep top `bestn` hits with a priority queue through all overlaps
    """
    rtn = {}
    for l in readlines():
        l = l.strip().split()
        q_id, t_id = l[:2]
        overlap_len = -int(l[2])
        idt = float(l[3])
        q_s, q_e, q_l = int(l[5]), int(l[6]), int(l[7])
        t_s, t_e, t_l = int(l[9]), int(l[10]), int(l[11])
        if t_l < min_len:
            continue
        if q_id not in rid_to_ctg:
            continue
        rtn.setdefault(t_id, [])
        if len(rtn[t_id]) < bestn:
            heappush(rtn[t_id], (overlap_len, q_id))
        else:
            heappushpop(rtn[t_id], (overlap_len, q_id))

    return rtn


def run_track_reads(
        exe_pool, file_list, min_len, bestn, db_fn,
        output_fn,
):
    io.LOG('preparing tr_stage1')
    io.logstats()
    read_map_dir = '.'
    rid_to_ctg = get_rid_to_ctg(os.path.join(
        read_map_dir, 'get_read_ctg_map', 'read_to_contig_map'))
    inputs = []
    for fn in file_list:
        inputs.append((run_tr_stage1, db_fn, fn, min_len, bestn, rid_to_ctg))
    """
    Aggregate hits from each individual LAS and keep the best n hit.
    Note that this does not guarantee that the final results is globally the best n hits espcially
    when the number of `bestn` is too small.  In those case, if there is more hits from single LAS
    file, then we will miss some good  hits.
    """
    bread_to_areads = {}
    for fn, res in exe_pool.imap(io.run_func, inputs):
        for k in res:
            bread_to_areads.setdefault(k, [])
            for item in res[k]:
                if len(bread_to_areads[k]) < bestn:
                    heappush(bread_to_areads[k], item)
                else:
                    heappushpop(bread_to_areads[k], item)

    #rid_to_oid = open(os.path.join(rawread_dir, 'dump_rawread_ids', 'raw_read_ids')).read().split('\n')

    """
    For each b-read, we find the best contig map throgh the b->a->contig map.
    """
    with open(output_fn, 'w') as out_f:
        for bread in bread_to_areads:

            ctg_score = {}
            for s, rid in bread_to_areads[bread]:
                if rid not in rid_to_ctg:
                    continue

                ctgs = rid_to_ctg[rid]
                for ctg in ctgs:
                    ctg_score.setdefault(ctg, [0, 0])
                    ctg_score[ctg][0] += -s
                    ctg_score[ctg][1] += 1

            #oid = rid_to_oid[int(bread)]
            ctg_score = list(ctg_score.items())
            ctg_score.sort(key=lambda k: k[1][0])
            rank = 0

            for ctg, score_count in ctg_score:
                if bread in rid_to_ctg and ctg in rid_to_ctg[bread]:
                    in_ctg = 1
                else:
                    in_ctg = 0
                score, count = score_count
                #print(bread, oid, ctg, count, rank, score, in_ctg, file=out_f)
                print(bread, ctg, count, rank, score, in_ctg, file=out_f)
                rank += 1


def try_run_track_reads(
    n_core, min_len, bestn,
    db_fn, las_fofn_fn,
    output_fn,
):
    io.LOG('starting track_reads')

    file_list = list(io.yield_validated_fns(las_fofn_fn))
    io.LOG('file list: %r' % file_list)

    # same, shoud we decide this as a parameter
    n_core = min(n_core, len(file_list))
    exe_pool = Pool(n_core)
    try:
        run_track_reads(exe_pool, file_list, min_len, bestn, db_fn, output_fn)
        io.LOG('finished track_reads')
    except:
        io.LOG('terminating track_reads workers...')
        exe_pool.terminate()
        raise


def track_reads(
        n_core, min_len, bestn, debug, silent, stream,
        base_dir, db_fn, las_fofn_fn,
        output_fn,
):
    if debug:
        n_core = 0
        silent = False
    if silent:
        io.LOG = io.write_nothing
    if stream:
        global Reader
        Reader = io.StreamedProcessReaderContext

    try_run_track_reads(n_core, min_len, bestn, db_fn, las_fofn_fn, output_fn)


def parse_args(argv):
    description = """
Using a dazzler db,
scan the raw read overlap information (in .las files),
to identify the best hit from the reads
to the contigs with file generated by `fc_get_read_ctg_map` in `./get_read_ctg_map/read_to_contig_map`
"""
    parser = argparse.ArgumentParser(description=description,
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument(
        '--n-core', type=int, default=4,
        help='number of processes used for for tracking reads; '
        '0 for main process only')
    parser.add_argument(
        '--base-dir', type=str, default='.',
        help='Substituted as {base_dir} into default inputs.')
    parser.add_argument(
        '--db-fn', type=str, default='{base_dir}/0-rawreads/build/raw_reads.db',
        help='Input. Filename of Dazzler DB')
    parser.add_argument(
        '--las-fofn-fn', type=str, default='{base_dir}/0-rawreads/las-merge-combine/las_fofn.json',
        help='Inputs. Filename of las filenames, to be processed in parallel. Paths are relative to location of file.')
    parser.add_argument(
        '--min-len', type=int, default=2500,
        help="min length of the reads")
    parser.add_argument(
        '--stream', action='store_true',
        help='stream from LA4Falcon, instead of slurping all at once; can save memory for large data')
    parser.add_argument(
        '--debug', '-g', action='store_true',
        help="single-threaded, plus other aids to debugging")
    parser.add_argument(
        '--silent', action='store_true',
        help="suppress cmd reporting on stderr")
    parser.add_argument(
        '--bestn', type=int, default=40,
        help="keep best n hits")
    parser.add_argument(
        '--output-fn', default='./3-unzip/reads/rawread_to_contigs',
        help="best hits from rawreads")
    args = parser.parse_args(argv[1:])
    args.db_fn = args.db_fn.format(**vars(args))
    args.las_fofn_fn = args.las_fofn_fn.format(**vars(args))
    return args


def main(argv=sys.argv):
    args = parse_args(argv)
    track_reads(**vars(args))


if __name__ == "__main__":
    main()
