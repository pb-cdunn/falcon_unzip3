from pypeflow.simple_pwatcher_bridge import (
    makePypeLocalFile, fn,
    PypeTask,
)
from falcon_kit.FastaReader import FastaReader
from .. import io
import json
import logging
import os

LOG = logging.getLogger(__name__)


def task_track_reads_h(self):
    input_bam_fofn = fn(self.input_bam_fofn)
    rawread_to_contigs = fn(self.rawread_to_contigs)
    abs_rawread_to_contigs = os.path.abspath(rawread_to_contigs)
    job_done = fn(self.job_done)
    topdir = os.path.relpath(self.parameters['topdir'])
    basedir = os.path.relpath(topdir)
    reldir = os.path.relpath('.', topdir)
    script_fn = 'track_reads_h.sh'

    # For now, in/outputs are in various directories, by convention, including '0-rawreads/m_*/*.msgpack'
    script = """\
set -vex
trap 'touch {job_done}.exit' EXIT
hostname
date

python -m falcon_unzip.mains.get_read_hctg_map --base-dir={basedir} --output=read_to_contig_map
# formerly generated ./4-quiver/read_maps/read_to_contig_map

fc_rr_hctg_track.py --base-dir={basedir} --stream
# That writes into 0-rawreads/m_*/

cd {topdir}
fc_rr_hctg_track2.exe --output={abs_rawread_to_contigs}
cd -

date
ls -l {rawread_to_contigs}
touch {job_done}
""".format(**locals())

    with open(script_fn, 'w') as script_file:
        script_file.write(script)
    self.generated_script_fn = script_fn


def task_select_reads_h(self):
    read2ctg = fn(self.read2ctg)
    input_bam_fofn = fn(self.input_bam_fofn)
    topdir = os.path.relpath(self.parameters['topdir'])
    script_fn = 'select_reads_h.sh'

    # For now, in/outputs are in various directories, by convention.
    script = """\
set -vex
hostname
date

cd {topdir}
pwd
python -m falcon_unzip.mains.get_read2ctg --output={read2ctg} {input_bam_fofn}

date
cd -
""".format(**locals())

    with open(script_fn, 'w') as script_file:
        script_file.write(script)
    self.generated_script_fn = script_fn


def task_merge_reads(self):
    merged_fofn = fn(self.merged_fofn)
    read2ctg = fn(self.read2ctg)
    input_bam_fofn = fn(self.input_bam_fofn)
    max_n_open_files = self.parameters['max_n_open_files']
    topdir = os.path.relpath(self.parameters['topdir'])
    script_fn = 'merge_reads.sh'

    # For now, in/outputs are in various directories, by convention.
    script = """\
set -vex
#trap 'touch {merged_fofn}.exit' EXIT
hostname
date

cd {topdir}
#fc_select_reads_from_bam.py --max-n-open-files={max_n_open_files} {input_bam_fofn}
pwd
python -m falcon_unzip.mains.bam_partition_and_merge --max-n-open-files={max_n_open_files} --read2ctg-fn={read2ctg} --merged-fn={merged_fofn} {input_bam_fofn}

date
cd -
# Expect {merged_fofn}
""".format(**locals())

    with open(script_fn, 'w') as script_file:
        script_file.write(script)
    self.generated_script_fn = script_fn


def task_run_quiver(self):
    ref_fasta = fn(self.ref_fasta)
    read_bam = fn(self.read_bam)

    cns_fasta = fn(self.cns_fasta)
    cns_fastq = fn(self.cns_fastq)
    job_done = fn(self.job_done)

    job_uid = self.parameters['job_uid']
    ctg_id = self.parameters['ctg_id']

    # TODO: tmpdir

    script_fn = 'cns_%s.sh' % (ctg_id)
    script = """\
set -vex
trap 'touch {job_done}.exit' EXIT
hostname
date

samtools faidx {ref_fasta}
pbalign --tmpDir=/localdisk/scratch/ --nproc=24 --minAccuracy=0.75 --minLength=50\
          --minAnchorSize=12 --maxDivergence=30 --concordant --algorithm=blasr\
          --algorithmOptions=--useQuality --maxHits=1 --hitPolicy=random --seed=1\
            {read_bam} {ref_fasta} aln-{ctg_id}.bam
#python -c 'import ConsensusCore2 as cc2; print cc2' # So quiver likely works.
(variantCaller --algorithm=arrow -x 5 -X 120 -q 20 -j 24 -r {ref_fasta} aln-{ctg_id}.bam\
            -o {cns_fasta} -o {cns_fastq}) || echo WARNING quiver failed. Maybe no reads for this block.
date
touch {job_done}
""".format(**locals())

    with open(script_fn, 'w') as script_file:
        script_file.write(script)
    self.generated_script_fn = script_fn


def task_cns_zcat(self):
    gathered_p_ctg = fn(self.gathered_p_ctg)
    gathered_h_ctg = fn(self.gathered_h_ctg)
    cns_p_ctg_fasta = fn(self.cns_p_ctg_fasta)
    cns_p_ctg_fastq = fn(self.cns_p_ctg_fastq)
    cns_h_ctg_fasta = fn(self.cns_h_ctg_fasta)
    cns_h_ctg_fastq = fn(self.cns_h_ctg_fastq)

    script_fn = 'cns_zcat.sh'
    script = """\
python -m falcon_unzip.mains.cns_zcat \
    --gathered-p-ctg-fn={gathered_p_ctg} \
    --gathered-h-ctg-fn={gathered_h_ctg} \
    --cns-p-ctg-fasta-fn={cns_p_ctg_fasta} \
    --cns-p-ctg-fastq-fn={cns_p_ctg_fastq} \
    --cns-h-ctg-fasta-fn={cns_h_ctg_fasta} \
    --cns-h-ctg-fastq-fn={cns_h_ctg_fastq} \

""".format(**locals())

    with open(script_fn, 'w') as script_file:
        script_file.write(script)
    self.generated_script_fn = script_fn


def task_scatter_quiver(self):
    p_ctg_fn = fn(self.p_ctg_fa)
    h_ctg_fn = fn(self.h_ctg_fa)
    out_json = fn(self.scattered_quiver_json)
    ctg2bamfn_fn = fn(self.ctg2bamfn)
    config = self.parameters['config']

    ctg2bamfn = io.deserialize(ctg2bamfn_fn)

    ref_seq_data = {}

    # I think this will crash if the file is empty. Maybe that is ok.
    p_ctg_fa = FastaReader(p_ctg_fn)
    ctg_types = {}
    for r in p_ctg_fa:
        rid = r.name.split()[0]
        ref_seq_data[rid] = r.sequence
        ctg_types[rid] = 'p'

    # I think this will crash if the file is empty. Maybe that is ok.
    h_ctg_fa = FastaReader(h_ctg_fn)
    for r in h_ctg_fa:
        rid = r.name.split()[0]
        ref_seq_data[rid] = r.sequence
        ctg_types[rid] = 'h'

    ctg_ids = sorted(ref_seq_data.keys())
    # p_ctg_out=[]
    # h_ctg_out=[]
    #job_done_plfs = {}
    jobs = []
    for ctg_id in ctg_ids:
        sequence = ref_seq_data[ctg_id]
        m_ctg_id = ctg_id.split('-')[0]
        wd = os.path.join(os.getcwd(), m_ctg_id)
        ref_fasta = os.path.join(wd, '{ctg_id}_ref.fa'.format(ctg_id=ctg_id))
        #cns_fasta = makePypeLocalFile(os.path.join(wd, 'cns-{ctg_id}.fasta.gz'.format(ctg_id = ctg_id)))
        #cns_fastq = makePypeLocalFile(os.path.join(wd, 'cns-{ctg_id}.fastq.gz'.format(ctg_id = ctg_id)))
        #job_done = makePypeLocalFile(os.path.join(wd, '{ctg_id}_quiver_done'.format(ctg_id = ctg_id)))
        ctg_types2 = {}
        ctg_types2[ctg_id] = ctg_types[ctg_id]

        # if os.path.exists(read_bam):
        if ctg_id in ctg2bamfn:
            read_bam = ctg2bamfn[ctg_id]
            # The segregated *.sam are created in task_segregate.
            # Network latency should not matter because we have already waited for the 'done' file.
            io.mkdirs(wd)
            if not os.path.exists(ref_fasta):
                # TODO(CD): Up to 50MB of seq data. Should do this on remote host.
                #   See https://github.com/PacificBiosciences/FALCON_unzip/issues/59
                with open(ref_fasta, 'w') as f:
                    print >>f, '>' + ctg_id
                    print >>f, sequence
            new_job = {}
            new_job['ctg_id'] = ctg_id
            new_job['ctg_types'] = ctg_types2
            new_job['smrt_bin'] = config['smrt_bin']
            new_job['sge_option'] = config['sge_quiver']
            new_job['ref_fasta'] = ref_fasta
            new_job['read_bam'] = read_bam
            jobs.append(new_job)
    io.serialize(out_json, jobs)


def task_gather_quiver(self):
    """We wrote the "gathered" files during task construction.
    """
    job_done_fn = fn(self.job_done)
    io.touch(job_done_fn)


def task_segregate_scatter(self):
    merged_fofn_fn = fn(self.merged_fofn)
    scattered_segregate_json_fn = fn(self.scattered_segregate_json)

    LOG.info('Scatting segregate-reads tasks. Reading merged BAM names from FOFN: {!r}'.format(
        merged_fofn_fn))
    fns = list(io.yield_abspath_from_fofn(merged_fofn_fn))
    jobs = list()
    for i, merged_bamfn in enumerate(fns):
        job = dict()
        job['merged_bamfn'] = merged_bamfn
        job_name = 'segr{:03d}'.format(i)
        job['job_name'] = job_name
        jobs.append(job)

    io.serialize(scattered_segregate_json_fn, jobs)
    # Fast (for now), so do it locally.


def task_run_segregate(self):
    # max_n_open_files = 300 # Ignored for now. Should not matter here.
    merged_bamfn = fn(self.merged_bamfn)
    segregated_bam_fofn = fn(self.segregated_bam_fofn)

    script = """
python -m falcon_unzip.mains.bam_segregate --merged-fn={merged_bamfn} --output-fn={segregated_bam_fofn}
""".format(**locals())

    script_fn = 'run_bam_segregate.sh'
    with open(script_fn, 'w') as script_file:
        script_file.write(script)
    self.generated_script_fn = script_fn


def task_segregate_gather(self):
    jn2segregated_bam_fofn = self.inputs
    ctg2segregated_bamfn_fn = fn(self.ctg2segregated_bamfn)

    ctg2segregated_bamfn = dict()
    for jn, plf in jn2segregated_bam_fofn.iteritems():
        # We do not really care about the arbitrary job-name.
        fofn_fn = fn(plf)
        # Read FOFN.
        segregated_bam_fns = list(io.yield_abspath_from_fofn(fofn_fn))
        # Discern ctgs from filepaths.
        for bamfn in segregated_bam_fns:
            basename = os.path.basename(bamfn)
            ctg = os.path.splitext(basename)[0]
            ctg2segregated_bamfn[ctg] = bamfn
    io.serialize(ctg2segregated_bamfn_fn, ctg2segregated_bamfn)
    io.serialize(ctg2segregated_bamfn_fn + '.json', ctg2segregated_bamfn)  # for debugging
    # Do not generate a script. This is light and fast, so do it locally.


def get_track_reads_h_task(
        parameters, input_bam_fofn_plf, hasm_done_plf,
        track_reads_h_done_plf, track_reads_rr2c_plf,
):
    make_task = PypeTask(
        inputs={
            'input_bam_fofn': input_bam_fofn_plf,
            'hasm_done': hasm_done_plf,
        },
        outputs={
            'job_done': track_reads_h_done_plf,
            'rawread_to_contigs': track_reads_rr2c_plf,
        },
        parameters=parameters,
    )
    return make_task(task_track_reads_h)


def get_select_reads_h_task(
        parameters, track_reads_h_done_plf, input_bam_fofn_plf, hasm_done_plf,
        read2ctg_plf,
):
    make_task = PypeTask(inputs={
        # Some implicit inputs, plus these deps:
        'track_reads_h_done': track_reads_h_done_plf,
        'input_bam_fofn': input_bam_fofn_plf,
        'hasm_done': hasm_done_plf},
        outputs={
        'read2ctg': read2ctg_plf},
        parameters=parameters,
    )
    return make_task(task_select_reads_h)


def get_merge_reads_task(
        parameters, input_bam_fofn_plf, read2ctg_plf, merged_fofn_plf):
    make_task = PypeTask(inputs={
        'input_bam_fofn': input_bam_fofn_plf,
        'read2ctg': read2ctg_plf},
        outputs={
        'merged_fofn': merged_fofn_plf},
        parameters=parameters,
    )
    return make_task(task_merge_reads)


def get_segregate_scatter_task(
        parameters, merged_fofn_plf,
        scattered_segregate_plf,
):
    make_task = PypeTask(
        inputs={
            'merged_fofn': merged_fofn_plf,
        },
        outputs={
            'scattered_segregate_json': scattered_segregate_plf,
        },
        parameters=parameters,
    )
    return make_task(task_segregate_scatter)


def yield_segregate_bam_tasks(parameters, scattered_segregate_plf, ctg2segregated_bamfn_plf):
    # Segregate reads from merged BAM files in parallel.
    # (If this were not done in Python, it could probably be in serial.)

    jn2segregated_bam_fofn = dict()  # job_name -> FOFN_plf
    # ctg is encoded into each filepath within each FOFN.

    scattered_segregate_fn = fn(scattered_segregate_plf)
    jobs = io.deserialize(scattered_segregate_fn)
    basedir = os.path.dirname(scattered_segregate_fn)  # Should this be relative to cwd?
    for job in jobs:
        job_name = job['job_name']
        merged_bamfn_plf = makePypeLocalFile(job['merged_bamfn'])
        wd = os.path.join(basedir, job_name)
        # ctg is encoded into each filepath within the FOFN.
        segregated_bam_fofn_plf = makePypeLocalFile(os.path.join(wd, 'segregated_bam.fofn'))
        make_task = PypeTask(
            inputs={
                # The other input is next to this one, named by convention.
                'merged_bamfn': merged_bamfn_plf},
            outputs={
                'segregated_bam_fofn': segregated_bam_fofn_plf},
            parameters=parameters,
        )
        yield make_task(task_run_segregate)
        jn2segregated_bam_fofn[job_name] = segregated_bam_fofn_plf

    make_task = PypeTask(
        inputs=jn2segregated_bam_fofn,
        outputs={
            'ctg2segregated_bamfn': ctg2segregated_bamfn_plf,
        },
        parameters=parameters,
    )
    yield make_task(task_segregate_gather)


def get_scatter_quiver_task(
        parameters, ctg2segregated_bamfn_plf,
        scattered_quiver_plf,
):
    make_task = PypeTask(
        inputs={
            'p_ctg_fa': makePypeLocalFile('3-unzip/all_p_ctg.fa'), # TODO: make explicit
            'h_ctg_fa': makePypeLocalFile('3-unzip/all_h_ctg.fa'),
            'ctg2bamfn': ctg2segregated_bamfn_plf,
        },
        outputs={
            'scattered_quiver_json': scattered_quiver_plf,
        },
        parameters=parameters,
    )
    return make_task(task_scatter_quiver)

def yield_quiver_tasks(
        scattered_quiver_plf,
        gathered_p_ctg_plf, gathered_h_ctg_plf, gather_done_plf,
):
    scattered_quiver_fn = fn(scattered_quiver_plf)
    jobs = json.loads(open(scattered_quiver_fn).read())
    #ctg_ids = sorted(jobs['ref_seq_data'])
    p_ctg_out = []
    h_ctg_out = []
    job_done_plfs = {}
    for job in jobs:
        ctg_id = job['ctg_id']
        ctg_types = job['ctg_types']
        smrt_bin = job['smrt_bin']
        sge_option = job['sge_option']
        ref_fasta = makePypeLocalFile(job['ref_fasta'])
        read_bam = makePypeLocalFile(job['read_bam'])
        m_ctg_id = ctg_id.split('-')[0]
        wd = os.path.join(os.getcwd(), './4-quiver/', m_ctg_id)
        #ref_fasta = makePypeLocalFile(os.path.join(wd, '{ctg_id}_ref.fa'.format(ctg_id = ctg_id)))
        #read_bam = makePypeLocalFile(os.path.join(os.getcwd(), './4-quiver/reads/' '{ctg_id}.sam'.format(ctg_id = ctg_id)))
        cns_fasta = makePypeLocalFile(os.path.join(wd, 'cns-{ctg_id}.fasta.gz'.format(ctg_id=ctg_id)))
        cns_fastq = makePypeLocalFile(os.path.join(wd, 'cns-{ctg_id}.fastq.gz'.format(ctg_id=ctg_id)))
        job_done = makePypeLocalFile(os.path.join(wd, '{ctg_id}_quiver_done'.format(ctg_id=ctg_id)))

        if os.path.exists(fn(read_bam)):  # TODO(CD): Ask Jason what we should do if missing SAM.
            if ctg_types[ctg_id] == 'p':
                p_ctg_out.append((fn(cns_fasta), fn(cns_fastq)))
            elif ctg_types[ctg_id] == 'h':
                h_ctg_out.append((fn(cns_fasta), fn(cns_fastq)))
            else:
                LOG.warning('Type is {!r}, not "p" or "h". Why are we running Quiver?'.format(ctg_types[ctg_id]))
            parameters = {
                'job_uid': 'q-' + ctg_id,
                'ctg_id': ctg_id,
                'smrt_bin': smrt_bin,
                'sge_option': sge_option,
            }
            make_quiver_task = PypeTask(inputs={'ref_fasta': ref_fasta, 'read_bam': read_bam,
                                                'scattered_quiver': scattered_quiver_plf,
                                                },
                                        outputs={'cns_fasta': cns_fasta, 'cns_fastq': cns_fastq, 'job_done': job_done},
                                        parameters=parameters,
                                        )
            quiver_task = make_quiver_task(task_run_quiver)
            yield quiver_task
            job_done_plfs['{}'.format(ctg_id)] = job_done

    io.mkdirs(os.path.dirname(fn(gather_done_plf)))
    with open(fn(gathered_p_ctg_plf), 'w') as ifs:
        for cns_fasta_fn, cns_fastq_fn in sorted(p_ctg_out):
            ifs.write('{} {}\n'.format(cns_fasta_fn, cns_fastq_fn))
    with open(fn(gathered_h_ctg_plf), 'w') as ifs:
        for cns_fasta_fn, cns_fastq_fn in sorted(h_ctg_out):
            ifs.write('{} {}\n'.format(cns_fasta_fn, cns_fastq_fn))

    make_task = PypeTask(
        inputs=job_done_plfs,
        outputs={
            'job_done': gather_done_plf,
        },
        parameters={},
    )
    yield make_task(task_gather_quiver)


def get_cns_zcat_task(
        gathered_p_ctg_plf, gathered_h_ctg_plf,
        zcat_done_plf,
):
    cns_p_ctg_fasta_plf = makePypeLocalFile('4-quiver/cns_output/cns_p_ctg.fasta')
    cns_p_ctg_fastq_plf = makePypeLocalFile('4-quiver/cns_output/cns_p_ctg.fastq')
    cns_h_ctg_fasta_plf = makePypeLocalFile('4-quiver/cns_output/cns_h_ctg.fasta')
    cns_h_ctg_fastq_plf = makePypeLocalFile('4-quiver/cns_output/cns_h_ctg.fastq')
    make_task = PypeTask(
        inputs={
            'gathered_p_ctg': gathered_p_ctg_plf,
            'gathered_h_ctg': gathered_h_ctg_plf,
        },
        outputs={
            'cns_p_ctg_fasta': cns_p_ctg_fasta_plf,
            'cns_p_ctg_fastq': cns_p_ctg_fastq_plf,
            'cns_h_ctg_fasta': cns_h_ctg_fasta_plf,
            'cns_h_ctg_fastq': cns_h_ctg_fastq_plf,
            'job_done': zcat_done_plf,
        },
    )
    return make_task(task_cns_zcat)


def run_workflow(wf, config):
    abscwd = os.path.abspath('.')
    parameters = {
        'sge_option': config['sge_track_reads'],  # applies to select_reads task also, for now
        'max_n_open_files': config['max_n_open_files'],
        'topdir': os.getcwd(),
    }
    input_bam_fofn_fn = config['input_bam_fofn']
    input_bam_fofn_plf = makePypeLocalFile(input_bam_fofn_fn)
    hasm_done_plf = makePypeLocalFile('./3-unzip/1-hasm/hasm_done')  # by convention
    track_reads_h_done_plf = makePypeLocalFile('./4-quiver/track_reads/track_reads_h_done')
    track_reads_rr2c_plf = makePypeLocalFile('./4-quiver/track_reads/rawread_to_contigs')
    wf.addTask(get_track_reads_h_task(
        parameters, input_bam_fofn_plf, hasm_done_plf,
        track_reads_h_done_plf, track_reads_rr2c_plf))

    read2ctg_plf = makePypeLocalFile('./4-quiver/select_reads/read2ctg.msgpack')
    wf.addTask(get_select_reads_h_task(
        parameters, track_reads_h_done_plf, input_bam_fofn_plf, hasm_done_plf,
        read2ctg_plf))

    merged_fofn_plf = makePypeLocalFile('./4-quiver/merge_reads/merged.fofn')
    wf.addTask(get_merge_reads_task(
        parameters, input_bam_fofn_plf, read2ctg_plf, merged_fofn_plf))

    scattered_segregate_plf = makePypeLocalFile('./4-quiver/segregate_scatter/scattered.json')
    wf.addTask(get_segregate_scatter_task(
        parameters, merged_fofn_plf, scattered_segregate_plf))
    wf.refreshTargets()

    ctg2segregated_bamfn_plf = makePypeLocalFile('./4-quiver/segregate_gather/ctg2segregated_bamfn.msgpack')
    wf.addTasks(list(yield_segregate_bam_tasks(
        parameters, scattered_segregate_plf, ctg2segregated_bamfn_plf)))

    scattered_quiver_plf = makePypeLocalFile('4-quiver/quiver_scatter/scattered.json')
    parameters = {
        'config': config,
    }
    wf.addTask(get_scatter_quiver_task(
        parameters, ctg2segregated_bamfn_plf,
        scattered_quiver_plf,
        ))
    wf.refreshTargets()

    gathered_p_ctg_plf = makePypeLocalFile('4-quiver/cns_gather/p_ctg.txt')
    gathered_h_ctg_plf = makePypeLocalFile('4-quiver/cns_gather/h_ctg.txt')
    gather_done_plf = makePypeLocalFile('4-quiver/cns_gather/job_done')

    wf.addTasks(list(yield_quiver_tasks(
        scattered_quiver_plf,
        gathered_p_ctg_plf, gathered_h_ctg_plf, gather_done_plf)))

    zcat_done_plf = makePypeLocalFile('4-quiver/cns_output/job_done')

    wf.addTask(get_cns_zcat_task(
        gathered_p_ctg_plf, gathered_h_ctg_plf,
        zcat_done_plf))

    wf.refreshTargets()