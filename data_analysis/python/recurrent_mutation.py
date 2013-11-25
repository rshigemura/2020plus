from utils.python.amino_acid import AminoAcid
import utils.python.util as _utils
import pandas as pd
import pandas.io.sql as psql
import plot_data
from collections import Counter
import logging

logger = logging.getLogger(__name__)

def _count_recurrent_missense(hgvs_iterable):
    """Counts the total missense mutations and stratifies missense
    counts according to position.

    Args:
        hgvs_iterable (iterable): container object with HGVS protein strings

    Returns:
        gene_pos_ctr (dict): counts missense mutations by position.
                             {mutation_position: count, ...}
        total_missense_ctr (int): total missense mutation count

    NOTE: This function requires the input HGVS container to contain
    mutations only for a single gene.
    """
    gene_pos_ctr = {}
    total_missense_ctr = 0
    for hgvs in hgvs_iterable:
        aa = AminoAcid(hgvs)
        if aa.mutation_type == 'missense':
            gene_pos_ctr.setdefault(aa.pos, 0)
            gene_pos_ctr[aa.pos] += 1  # add 1 to dict of pos
            total_missense_ctr += 1  # add 1 to total missense
    return gene_pos_ctr, total_missense_ctr


def count_missense_types(hgvs_iterable, recurrent=2):
    """Count the number of recurrent missense and regular missense
    mutations given a threshold for recurrency.

    Args:
        hgvs_iterable (iterable): contains HGVS protein strings for a
                                  single gene.

    Kwargs:
        recurrent (int): threshold number of missense mutations to define
                         a recurrent position. (default=2)

    Returns:
        recurrent_cts (int): number of recurrent missense mutations in a gene
        missense_cts (int): number of regular missense mutations in a gene
    """
    pos_count, total_missense = _count_recurrent_missense(hgvs_iterable)
    recurrent_cts = sum([cts for cts in pos_count.values()
                         if cts >= recurrent])  # sum mutations passing theshold
    missense_cts = total_missense - recurrent_cts  # subtract reccurent from total
    return recurrent_cts, missense_cts


def count_recurrent_by_number(hgvs_iterable):
    """Count the number of recurrent positions with a given number recurrent
    counts."""
    pos_count, total_missense = _count_recurrent_missense(hgvs_iterable)
    mycounter = Counter(pos_count.values())
    return mycounter


def count_recurrent(conn):
    logger.info('Counting the number of recurrent positions . . .')

    # query database
    sql = "SELECT Gene, AminoAcid FROM nucleotide"  # get everything from table
    df = psql.frame_query(sql, con=conn)
    gene_to_indexes = df.groupby('Gene').groups

    # counters
    onco_ct = Counter()  # counter for oncogenes
    tsg_ct = Counter()  # counter for tumor suppressor genes
    all_ct = Counter()  # counter for all genes
    other_ct = Counter()  # counter for gene other than tsg/onco

    # count recurrent missense
    for gene, indexes in gene_to_indexes.iteritems():
        tmp_df = df.ix[indexes]
        myct = count_recurrent_by_number(tmp_df['AminoAcid'])
        all_ct += myct
        if gene in _utils.oncogene_set:
            onco_ct += myct
        elif gene in _utils.tsg_set:
            tsg_ct += myct
        else:
            other_ct += myct

    logger.info('Finished counting recurent.')
    return all_ct, onco_ct, tsg_ct, other_ct


def main(conn):
    cfg_opts = _utils.get_output_config('recurrent_mutation')

    # get count info
    all_counts, onco_counts, tsg_counts, other_counts = count_recurrent(conn)

    # extract count data
    all_indx, all_data = zip(*list(all_counts.iteritems()))
    onco_indx, onco_data = zip(*list(onco_counts.iteritems()))
    tsg_indx, tsg_data = zip(*list(tsg_counts.iteritems()))
    other_indx, other_data = zip(*list(other_counts.iteritems()))

    # create temporary data frames
    all_df = pd.DataFrame({'all': all_data},
                          index=all_indx)
    onco_df = pd.DataFrame({'oncogene': onco_data},
                           index=onco_indx)
    tsg_df = pd.DataFrame({'tsg': tsg_data},
                          index=tsg_indx)
    other_df = pd.DataFrame({'other': other_data},
                            index=other_indx)
    all_df.index.name = 'Number of Mutations'
    other_df.index.name = 'Number of Mutations'
    onco_df.index.name = 'Number of Mutations'
    tsg_df.index.name = 'Number of Mutations'

    # write output to file
    all_df.to_csv(_utils.result_dir + cfg_opts['all_recurrent'], sep='\t')
    onco_df.to_csv(_utils.result_dir + cfg_opts['onco_recurrent'], sep='\t')
    tsg_df.to_csv(_utils.result_dir + cfg_opts['tsg_recurrent'], sep='\t')
    other_df.to_csv(_utils.result_dir + cfg_opts['other_recurrent'], sep='\t')

    # add data to single dataframe for plotting purposes
    other_df['oncogene'] = onco_df['oncogene']
    other_df['tsg'] = tsg_df['tsg']

    # plot recurrent missense positions per gene
    tmp_path = _utils.plot_dir + cfg_opts['recur_missense_line']
    plot_data.recurrent_missense_pos_line(other_df,
                                          tmp_path)