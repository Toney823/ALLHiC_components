#!/usr/bin/env python
import argparse
import numpy as np
import matplotlib as mpl
import matplotlib.pyplot as plt
import pysam
import time
import os

mpl.use("Agg")


def time_print(info):
    print("\033[32m%s\033[0m %s"%(time.strftime('[%H:%M:%S]',time.localtime(time.time())), info))


def get_opts():
    groups = argparse.ArgumentParser()
    groups.add_argument('-b', '--bam', help='Input bam file', required=True)
    groups.add_argument('-l', '--list', help='Chromosome list, contain: ID\tLength', required=True)
    groups.add_argument('-n', '--npz', help="npz file of hic signal, optional, if this parameter is set but file "
                                            "not exist, it will be generate after reading hic signals, or it will "
                                            "be loaded for drawing other resolution of heatmap", default="")
    groups.add_argument('-m', '--min_size', help="Minium bin size of heatmap, default=50k", default="50k")
    groups.add_argument('-s', '--size', help="Bin size of heatmap, can be a list separated by comma, default=500k, "
                                             "notice: it must be n times of min_size (n is integer) or we will ajust "
                                             "it to nearest one", default="500k")
    groups.add_argument('-o', '--outdir', help='Output directory, default=workdir', default='workdir')
    groups.add_argument('--line', help='Draw dash line for each chromosome', action='store_true')

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


# Calc read counts on each bin
def calc_read_count_per_min_size(chr_len_db, chr_order, bam, min_size):
    long_bin_size=min_size
    read_count_whole_genome = {}
    
    bin_offset = [0 for i in range(0, len(chr_order)+1)]
    bin_count = [0 for i in range(0, len(chr_order)+1)]
    total_bin_count = 0
    
    for chrn in chr_len_db:
        bin_count_of_chr = int(round((chr_len_db[chrn]*1.0/long_bin_size+0.51)))
        total_bin_count += bin_count_of_chr
        bin_count[chr_order.index(chrn)+1] = bin_count_of_chr
    
    for i in range(1, len(bin_count)):
        bin_offset[i] = bin_count[i]+bin_offset[i-1]
    read_count_whole_genome = [[0 for i in range(0, total_bin_count)] for j in range(0, total_bin_count)]
    
    with pysam.AlignmentFile(bam, 'rb') as fin:
        for line in fin:
            if line.is_unmapped or line.mate_is_unmapped:
                continue
            chrn1 = line.reference_name
            chrn2 = line.next_reference_name
            if chrn1 not in chr_order or chrn2 not in chr_order:
                continue

            read_pos1 = line.reference_start+1
            read_pos2 = line.next_reference_start+1

            pos1_index = int(read_pos1/long_bin_size)
            pos2_index = int(read_pos2/long_bin_size)
            
            chr1_index = chr_order.index(chrn1)
            chr2_index = chr_order.index(chrn2)
            
            whole_pos1 = bin_offset[chr1_index] + pos1_index
            whole_pos2 = bin_offset[chr2_index] + pos2_index
            try:
                read_count_whole_genome[whole_pos1][whole_pos2] += 1
                read_count_whole_genome[whole_pos2][whole_pos1] += 1
            except IndexError:
                time_print("Index error on whole genome: index1: %d, index2: %d, bin counts: %d"%(whole_pos1, whole_pos2, total_bin_count))
    
    return np.array(bin_offset), np.array(read_count_whole_genome)


def draw_heatmap(read_count_whole_genome_min_size, bin_offset_min_size, ratio, chr_order, min_size, draw_line):
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
    cmap = plt.get_cmap("YlOrRd")
    cmap.set_over('black')
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
    if draw_line:
        idx = 1
        x_ticks = []
        y_ticks = []
        for _ in chr_order:
            sr = bin_offset_min_size[idx - 1] * 1. / ratio
            er = bin_offset_min_size[idx] * 1. / ratio
            mr = (sr+er) / 2.
            plt.plot((sr, sr), (0, plt_cnt), color='black', linestyle=':', lw=1)
            plt.plot((er, er), (0, plt_cnt), color='black', linestyle=':', lw=1)
            plt.plot((0, plt_cnt), (sr, sr), color='black', linestyle=':', lw=1)
            plt.plot((0, plt_cnt), (er, er), color='black', linestyle=':', lw=1)
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
        cmap = plt.get_cmap('YlOrRd')
        cmap.set_over('black')
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


def ALLHiC_plot(bam, chrlist, npzfile, minsize, binsize, draw_line, outdir):
    bam = os.path.abspath(bam)
    chrlist = os.path.abspath(chrlist)
    if npzfile != "":
        npzfile = os.path.abspath(npzfile)

    if not os.path.exists(outdir):
        os.mkdir(outdir)
    os.chdir(outdir)

    min_size = minsize.upper()
    min_size = min_size.replace('K', '000')
    min_size = min_size.replace('M', '000000')
    min_size = min_size.replace('G', '000000000')
    min_size = int(min_size)

    bin_list = binsize.split(',')
    bin_ratio = []
    for bin_size in bin_list:
        long_bin_size = bin_size.upper()
        long_bin_size = long_bin_size.replace('K', '000')
        long_bin_size = long_bin_size.replace('M', '000000')
        long_bin_size = long_bin_size.replace('G', '000000000')
        long_bin_size = int(long_bin_size)
        bin_ratio.append(int(round(long_bin_size/min_size+0.01, 0)))
        
    
    time_print("Step1: Get chromosome length")
    chr_len_db, chr_order = get_chr_len(chrlist)

    time_print("Step2: Get signal matrix")
    if npzfile != "" and os.path.exists(npzfile):
        npzdata = np.load(npzfile)
        bin_offset_min_size = npzdata['bin_offset_min_size']
        read_count_whole_genome_min_size = npzdata['read_count_whole_genome_min_size']
    else:
        bin_offset_min_size, read_count_whole_genome_min_size = calc_read_count_per_min_size(chr_len_db, chr_order,
                                                                                             bam, min_size)
        if npzfile != "":
            np.savez(npzfile.replace('.npz', ''), bin_offset_min_size=bin_offset_min_size,
                     read_count_whole_genome_min_size=read_count_whole_genome_min_size)
    
    time_print("Step3: Draw heatmap")
    
    for i in range(0, len(bin_ratio)):
        ratio = bin_ratio[i]
        time_print("Drawing with bin size %s" % bin_list[i])
        draw_heatmap(read_count_whole_genome_min_size, bin_offset_min_size, ratio, chr_order, min_size, draw_line)
    os.chdir('..')
    time_print("Success")


if __name__ == "__main__":
    opts = get_opts()
    bam = opts.bam
    chrlist = opts.list
    npzfile = opts.npz
    minsize = opts.min_size
    binsize = opts.size
    outdir = opts.outdir
    draw_line = opts.line
    ALLHiC_plot(bam, chrlist, npzfile, minsize, binsize, draw_line, outdir)
