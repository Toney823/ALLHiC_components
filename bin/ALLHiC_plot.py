#!/usr/bin/env python
import argparse
import numpy as np
import h5py
import matplotlib as mpl
import matplotlib.pyplot as plt
import multiprocessing
import ctypes
import functools
import pysam
import time
import os

mpl.use("Agg")


def time_print(info):
    print("\033[32m%s\033[0m %s" % (time.strftime('[%H:%M:%S]', time.localtime(time.time())), info))


def get_opts():
    groups = argparse.ArgumentParser()
    groups.add_argument('-b', '--bam', help='Input bam file', required=True)
    groups.add_argument('-l', '--list', help='Chromosome list, contain: ID\tLength', required=True)
    groups.add_argument('-a', '--agp', help='Input AGP file, if bam file is a contig-level mapping, agp file is '
                                            'required', default="")
    groups.add_argument('-5', '--h5',
                        help="h5 file of hic signal, optional, if not exist, it will be generate after reading "
                             "hic signals, or it will be loaded for drawing other resolution of heatmap",
                        default="")
    groups.add_argument('-m', '--min_size', help="Minium bin size of heatmap, default=50k", default="50k")
    groups.add_argument('-s', '--size',
                        help="Bin size of heatmap, can be a list separated by comma, default=500k, notice: it must "
                             "be n times of min_size (n is integer) or we will adjust it to nearest one",
                        default="500k")
    groups.add_argument('-c', '--cmap', help='CMAP for drawing heatmap, default="YlOrRd"', default='YlOrRd')
    groups.add_argument('-o', '--outdir', help='Output directory, default=workdir', default='workdir')
    groups_ex = groups.add_mutually_exclusive_group()
    groups_ex.add_argument('--line', help='Draw dash line for each chromosome', action='store_true')
    groups_ex.add_argument('--block', help='Draw dash block for each chromosome', action='store_true')
    groups.add_argument('--linecolor', help='Color of dash line or dash block, default="grey"', default='grey')
    groups.add_argument('-t', '--thread', help='Threads for reading bam, default=1', type=int, default=1)
    return groups.parse_args()


def long2short(bin_size: int) -> str:
    bin_size = str(bin_size)
    short_bin_size = ""
    if bin_size[-9:] == '000000000':
        short_bin_size = bin_size[:-9] + 'G'
    elif bin_size[-6:] == '000000':
        short_bin_size = bin_size[:-6] + 'M'
    elif bin_size[-3:] == '000':
        short_bin_size = bin_size[:-3] + 'K'
    return short_bin_size


def short2long(bin_size: str) -> int:
    long_bin_size = bin_size.upper()
    long_bin_size = long_bin_size.replace('K', '000')
    long_bin_size = long_bin_size.replace('M', '000000')
    long_bin_size = long_bin_size.replace('G', '000000000')
    long_bin_size = int(long_bin_size)
    return long_bin_size


# Get chromosome length
def get_chr_len(chr_list):
    chr_len_db = {}
    chr_order = []
    with open(chr_list, 'r') as f_in:
        for line in f_in:
            if line.strip() == '':
                continue
            data = line.strip().split()
            chr_order.append(data[0])
            chr_len_db[data[0]] = int(data[1])
    return chr_len_db, chr_order


# Init global shared array
def init_pool(bin_offset, read_count_whole_genome):
    global shared_bin_offset
    shared_bin_offset = bin_offset
    global shared_read_count_whole_genome
    shared_read_count_whole_genome = read_count_whole_genome


# agp reader
def load_agp(agp):
    ctg_on_chr = {}
    with open(agp, 'r') as f_in:
        for line in f_in:
            if line.strip() == '' or line[0] == '#':
                continue
            data = line.strip().split()
            if data[4] == 'U':
                continue
            chrn = data[0]
            start_pos = int(data[1])
            end_pos = int(data[2])
            ctg = data[5].replace('_pilon', '')
            direct = data[-1]
            ctg_on_chr[ctg] = [chrn, start_pos, end_pos, direct]
    return ctg_on_chr


# bam reader with agp
def bam_read_with_agp(agp, chr_list, bam, long_bin_size, total_bin_count, i):
    ctg_on_chr = load_agp(agp)
    chr_len_db, chr_order = get_chr_len(chr_list)
    ctg_list = sorted(ctg_on_chr)
    with pysam.AlignmentFile(bam, 'rb') as fin:
        for line in fin.fetch(contig=ctg_list[i]):
            if line.is_unmapped or line.mate_is_unmapped:
                continue
            ctg1 = line.reference_name
            ctg2 = line.next_reference_name
            read_pos1 = line.reference_start + 1
            read_pos2 = line.next_reference_start + 1

            if ctg1 not in ctg_on_chr or ctg2 not in ctg_on_chr:
                continue
            chrn1, ctg_start_pos1, ctg_end_pos1, ctg_direct1 = ctg_on_chr[ctg1]
            chrn2, ctg_start_pos2, ctg_end_pos2, ctg_direct2 = ctg_on_chr[ctg2]
            if ctg_direct1 == '+':
                converted_pos1 = ctg_start_pos1 + read_pos1 - 1
            else:
                converted_pos1 = ctg_end_pos1 - read_pos1 + 1
            if ctg_direct2 == '+':
                converted_pos2 = ctg_start_pos2 + read_pos2 - 1
            else:
                converted_pos2 = ctg_end_pos2 - read_pos2 + 1
            if chrn1 not in chr_len_db or chrn2 not in chr_len_db:
                continue
            pos1_index = int(converted_pos1 / long_bin_size)
            pos2_index = int(converted_pos2 / long_bin_size)

            chr1_index = chr_order.index(chrn1)
            chr2_index = chr_order.index(chrn2)

            bin_offset = np.frombuffer(shared_bin_offset, dtype=ctypes.c_int)

            whole_pos1 = bin_offset[chr1_index] + pos1_index
            whole_pos2 = bin_offset[chr2_index] + pos2_index

            read_count_whole_genome = np.frombuffer(shared_read_count_whole_genome,
                                                    dtype=ctypes.c_double).reshape(total_bin_count, total_bin_count)
            read_count_whole_genome[whole_pos1][whole_pos2] += 1
            read_count_whole_genome[whole_pos2][whole_pos1] += 1


# bam reader without agp
def bam_read_no_agp(chr_list, bam, long_bin_size, total_bin_count, i):
    _, chr_order = get_chr_len(chr_list)
    with pysam.AlignmentFile(bam, 'rb') as fin:
        for line in fin.fetch(contig=chr_order[i]):
            if line.is_unmapped or line.mate_is_unmapped:
                continue
            chrn1 = line.reference_name
            chrn2 = line.next_reference_name
            if chrn1 not in chr_order or chrn2 not in chr_order:
                continue

            read_pos1 = line.reference_start + 1
            read_pos2 = line.next_reference_start + 1

            pos1_index = int(read_pos1 / long_bin_size)
            pos2_index = int(read_pos2 / long_bin_size)

            chr1_index = chr_order.index(chrn1)
            chr2_index = chr_order.index(chrn2)

            bin_offset = np.frombuffer(shared_bin_offset, dtype=ctypes.c_int)

            whole_pos1 = bin_offset[chr1_index] + pos1_index
            whole_pos2 = bin_offset[chr2_index] + pos2_index
            read_count_whole_genome = np.frombuffer(shared_read_count_whole_genome,
                                                    dtype=ctypes.c_double).reshape(total_bin_count, total_bin_count)
            read_count_whole_genome[whole_pos1][whole_pos2] += 1
            read_count_whole_genome[whole_pos2][whole_pos1] += 1


# Calc read counts on each bin
def calc_read_count_per_min_size(chr_list, bam, agp, min_size, thread):
    long_bin_size = min_size

    chr_len_db, chr_order = get_chr_len(chr_list)
    bin_offset = [0 for i in range(0, len(chr_order) + 1)]
    bin_count = [0 for i in range(0, len(chr_order) + 1)]
    total_bin_count = 0

    for chrn in chr_len_db:
        bin_count_of_chr = int(round((chr_len_db[chrn] * 1.0 / long_bin_size + 0.51)))
        total_bin_count += bin_count_of_chr
        bin_count[chr_order.index(chrn) + 1] = bin_count_of_chr

    for i in range(1, len(bin_count)):
        bin_offset[i] = bin_count[i] + bin_offset[i - 1]

    bin_offset_base = multiprocessing.RawArray(ctypes.c_int, np.array(bin_offset))
    read_count_whole_genome_base = multiprocessing.RawArray(ctypes.c_double, total_bin_count * total_bin_count)

    # because of the hic signal is sparse between chromosomes, means the reads pair read by different process
    # unlikely locate in same bin, that means different process unlikely write same bin at same time, so we do
    # not use lock to avoid data write in same bin.
    if agp:
        ctg_cnt = len(load_agp(agp))
        if thread > ctg_cnt:
            time_print("Threads is larger than need, reduce to %d" % ctg_cnt)
            thread = ctg_cnt
        partial_bam_read_with_agp = functools.partial(bam_read_with_agp, agp, chr_list, bam,
                                                      long_bin_size, total_bin_count)
        pool = multiprocessing.Pool(processes=thread, initializer=init_pool,
                                    initargs=(bin_offset_base, read_count_whole_genome_base))
        pool.map(partial_bam_read_with_agp, range(ctg_cnt))
    else:
        chr_cnt = len(chr_order)
        if thread > chr_cnt:
            time_print("Threads is larger than need, reduce to %d" % chr_cnt)
            thread = chr_cnt
        partial_bam_read_no_agp = functools.partial(bam_read_no_agp, chr_list, bam, long_bin_size, total_bin_count)
        pool = multiprocessing.Pool(processes=thread, initializer=init_pool,
                                    initargs=(bin_offset_base, read_count_whole_genome_base))
        pool.map(partial_bam_read_no_agp, range(chr_cnt))

    return np.array(bin_offset), np.array(np.frombuffer(read_count_whole_genome_base,
                                                        dtype=ctypes.c_double).reshape(total_bin_count,
                                                                                       total_bin_count))


def draw_heatmap(read_count_whole_genome_min_size, bin_offset_min_size,
                 ratio, chr_order, min_size, cmap, draw_line, draw_block,
                 line_color):
    bin_size = int(ratio * min_size)
    short_bin_size = long2short(bin_size)

    total_cnt = len(read_count_whole_genome_min_size)
    ratio_cnt = int(round(total_cnt * 1.0 / ratio + 0.51, 0))
    plt_cnt = int(total_cnt * 1.0 / ratio)

    data = read_count_whole_genome_min_size

    data = np.pad(data, ((0, ratio_cnt * ratio - total_cnt), (0, ratio_cnt * ratio - total_cnt)), 'constant',
                  constant_values=0)
    data = data.reshape(-1, ratio_cnt, ratio).sum(axis=2)
    data = data.reshape(ratio_cnt, -1, ratio_cnt).sum(axis=1)

    fn = "%s_Whole_genome.pdf" % short_bin_size
    cmap = plt.get_cmap(cmap)
    ax = plt.gca()
    with np.errstate(divide='ignore'):
        hmap = ax.imshow(np.log2(data[: plt_cnt, : plt_cnt]), interpolation='nearest', origin='lower', cmap=cmap,
                         aspect='equal')

    plt.colorbar(mappable=hmap, cax=None, ax=None, shrink=0.5)
    plt.tick_params(labelsize=6)
    for ticks in ax.get_xticklabels():
        ticks.set_rotation(90)
    for ticks in ax.get_yticklabels():
        ticks.set_rotation(0)
    title = 'Whole_genome_' + short_bin_size
    plt.xlabel("Bins (" + short_bin_size.lower() + "b per bin)", fontsize=8)
    if draw_line or draw_block:
        idx = 1
        x_ticks = []
        y_ticks = []
        for _ in chr_order:
            sr = bin_offset_min_size[idx - 1] * 1. / ratio
            er = bin_offset_min_size[idx] * 1. / ratio
            mr = (sr + er) / 2.
            if draw_line:
                plt.plot((sr, sr), (0, plt_cnt), color=line_color, linestyle=':', lw=.5)
                plt.plot((er, er), (0, plt_cnt), color=line_color, linestyle=':', lw=.5)
                plt.plot((0, plt_cnt), (sr, sr), color=line_color, linestyle=':', lw=.5)
                plt.plot((0, plt_cnt), (er, er), color=line_color, linestyle=':', lw=.5)
            else:
                plt.plot((sr, sr), (sr, er), color=line_color, linestyle=':', lw=.5)
                plt.plot((er, er), (sr, er), color=line_color, linestyle=':', lw=.5)
                plt.plot((sr, er), (sr, sr), color=line_color, linestyle=':', lw=.5)
                plt.plot((sr, er), (er, er), color=line_color, linestyle=':', lw=.5)
            x_ticks.append(mr)
            y_ticks.append(mr)
            idx += 1

        plt.xticks(x_ticks, chr_order)
        plt.yticks(y_ticks, chr_order)
        plt.xlim(0, plt_cnt)
        plt.ylim(0, plt_cnt)
    else:
        plt.xticks([])
        plt.yticks([])
    plt.title(title, y=1.01, fontsize=12)
    plt.savefig(fn, bbox_inches='tight', dpi=200)
    plt.close('all')

    chr_cnt = len(chr_order)
    row_cnt = int(round(np.sqrt(chr_cnt) + 0.51))
    col_cnt = int(round(chr_cnt * 1.0 / row_cnt + 0.51))
    all_fn = '%s_all_chrs.pdf' % short_bin_size
    plt.figure(figsize=(col_cnt * 2, row_cnt * 2))
    idx = 1
    for chrn in chr_order:
        sr = bin_offset_min_size[idx - 1]
        er = bin_offset_min_size[idx]
        sub_data = read_count_whole_genome_min_size[sr: er, sr: er]
        total_cnt = len(sub_data)
        ratio_cnt = int(round(total_cnt * 1.0 / ratio + 0.51, 0))
        plt_cnt = int(total_cnt * 1.0 / ratio)

        sub_data = np.pad(sub_data, ((0, ratio_cnt * ratio - total_cnt), (0, ratio_cnt * ratio - total_cnt)),
                          'constant', constant_values=0)
        sub_data = sub_data.reshape(-1, ratio_cnt, ratio).sum(axis=2)
        sub_data = sub_data.reshape(ratio_cnt, -1, ratio_cnt).sum(axis=1)

        plt.subplot(row_cnt, col_cnt, idx)
        ax = plt.gca()
        with np.errstate(divide='ignore'):
            hmap = ax.imshow(np.log2(sub_data[: plt_cnt, : plt_cnt]), interpolation='nearest', origin='lower',
                             cmap=cmap, aspect='equal')
        plt.colorbar(mappable=hmap, cax=None, ax=None, shrink=0.5)
        plt.tick_params(labelsize=5)
        plt.title(chrn)
        idx += 1

    plt.subplots_adjust(left=None, bottom=None, right=None, top=None, wspace=0.5, hspace=0.5)
    plt.savefig(all_fn, bbox_inches='tight', dpi=200)
    plt.close('all')


def ALLHiC_plot(bam, agp, chr_list, h5_file, minsize, binsize, cmap, draw_line, draw_block,
                line_color, out_dir, thread):
    bam_file = os.path.abspath(bam)
    if agp:
        agp_file = os.path.abspath(agp)
    else:
        agp_file = agp
    chr_list = os.path.abspath(chr_list)
    if h5_file != "":
        h5_file = os.path.abspath(h5_file)

    if not os.path.exists(out_dir):
        os.mkdir(out_dir)
    os.chdir(out_dir)

    min_size = short2long(minsize)

    bin_list = binsize.split(',')
    bin_ratio = []
    for bin_size in bin_list:
        long_bin_size = short2long(bin_size)
        bin_ratio.append(int(round(long_bin_size / min_size + 0.01, 0)))

    time_print("Step1: Get chromosome length")
    chr_len_db, chr_order = get_chr_len(chr_list)

    time_print("Step2: Get signal matrix")
    if h5_file != "" and os.path.exists(h5_file):
        h5_data = h5py.File(h5_file, 'r')
        bin_offset_min_size = h5_data['bin_offset_min_size']
        read_count_whole_genome_min_size = h5_data['read_count_whole_genome_min_size']
    else:
        bin_offset_min_size, read_count_whole_genome_min_size = calc_read_count_per_min_size(chr_list, bam_file,
                                                                                             agp_file, min_size,
                                                                                             thread)
        if h5_file != "":
            h5 = h5py.File(h5_file, 'w')
            h5.create_dataset('bin_offset_min_size', data=bin_offset_min_size)
            h5.create_dataset('read_count_whole_genome_min_size', data=read_count_whole_genome_min_size)

    time_print("Step3: Draw heatmap")

    for i in range(0, len(bin_ratio)):
        ratio = bin_ratio[i]
        time_print("Drawing with bin size %s" % bin_list[i])
        draw_heatmap(read_count_whole_genome_min_size, bin_offset_min_size,
                     ratio, chr_order, min_size, cmap, draw_line, draw_block,
                     line_color)
    os.chdir('..')
    time_print("Success")


if __name__ == "__main__":
    opts = get_opts()
    bam = opts.bam
    agp = opts.agp
    chr_list = opts.list
    h5_file = opts.h5
    minsize = opts.min_size
    binsize = opts.size
    cmap = opts.cmap
    out_dir = opts.outdir
    draw_line = opts.line
    draw_block = opts.block
    line_color = opts.linecolor
    thread = opts.thread
    ALLHiC_plot(bam, agp, chr_list, h5_file, minsize, binsize, cmap, draw_line, draw_block, line_color, out_dir, thread)
