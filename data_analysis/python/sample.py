"""
The sample module analyzes characteristics of samples in
the COSMIC database by using the cosmic_mutation.
"""

import utils.python.util as _utils
from utils.python.amino_acid import AminoAcid
import pandas.io.sql as psql
import plot_data
import pandas as pd
import numpy as np
import logging

logger = logging.getLogger(__name__)

def count_mutated_genes(conn):
    """Count the number of genes that are mutated in each sample.

    **Parameters**

    conn : MySQLdb connection
        connection to COSMIC_nuc

    **Returns**

    df : pd.DataFrame
        two column data frame of sample names and gene cts
    """
    sql = ('SELECT x.Tumor_Sample, SUM(x.gene_indicator) as GeneCounts'
          ' FROM ('
          '     SELECT Tumor_Sample, Gene, 1 as gene_indicator'
          '     FROM mutation'
          '     GROUP BY Tumor_Sample, Gene'
          ' ) x GROUP BY Tumor_Sample'
          ' ORDER BY GeneCounts Desc;')
    df = psql.frame_query(sql, con=conn)
    df.GeneCounts = df.GeneCounts.astype(int)  # pandas is not auto detecting
    return df


def count_mutations(conn):
    """Count the number of mutations in each sample.

    **Parameters**

    conn : MySQLdb connection
        connection to COSMIC_nuc

    **Returns**

    df : pd.DataFrame
        two column data frame of sample names and mutation cts
    """
    sql = ('SELECT x.Tumor_Sample, SUM(x.mut_indicator) as MutationCounts'
          ' FROM ('
          '     SELECT Tumor_Sample, 1 as mut_indicator'
          '     FROM mutation'
          ' ) x GROUP BY Tumor_Sample'
          ' ORDER BY MutationCounts Desc;')
    df = psql.frame_query(sql, con=conn)
    df.MutationCounts = df.MutationCounts.astype(int)  # pandas is not auto detecting
    return df


def count_per_gene(conn):
    sql = ('SELECT Gene, COUNT(DISTINCT(mut.Tumor_Sample)) as sample_count '
           'FROM mutation mut '
           'GROUP BY Gene')
    df = psql.frame_query(sql, con=conn)
    df.sample_count = df.sample_count.astype(int)
    return df


def gene_count_per_tumor_type(conn):
    sql = ('SELECT Gene, Tumor_Type, Tumor_Sample, Protein_Change as AminoAcid, '
           '       DNA_Change as Nucleotide, Variant_Classification '
           'FROM mutation')
    df = psql.frame_query(sql, con=conn)
    ttypes = df['Tumor_Type'].unique()
    cols = ['Gene', 'Tumor_type', 'sample_count']
    result_df = pd.DataFrame(columns=cols)
    for ttype in ttypes:
        # restrict to specific tumor type
        tmp_df = df[df['Tumor_Type']==ttype]

        # identify non-silent mutations
        non_silent = map(lambda x: AminoAcid(x).is_non_silent,
                         tmp_df['AminoAcid'])
        tmp_df['aa_non_silent'] = non_silent
        is_splice_site = tmp_df['Variant_Classification'] == 'Splice_Site'
        tmp_df['non_silent'] = (tmp_df['aa_non_silent'] | is_splice_site).astype(int)

        # calculate number of samples a gene has a non-silent mutation for
        # this specific tumor type
        table = pd.pivot_table(tmp_df,
                               values='non_silent',
                               cols='Tumor_Sample',
                               rows='Gene',
                               aggfunc=np.max)
        num_samples_per_gene = table.sum(axis=1)  # sum all samples for a gene

        # re-define tmp_df to create a dataframe to concatenate to the df
        # used save all of the results
        tmp_df = pd.DataFrame(columns=cols, index=num_samples_per_gene.index)
        tmp_df['sample_count'] = num_samples_per_gene
        tmp_df['Gene'] = tmp_df.index
        tmp_df['Tumor_Type'] = ttype  # add a col for tumor type

        # append results
        result_df = pd.concat([result_df, tmp_df])

    return result_df


def count_samples_per_tumor_type(conn):
    sql = ('SELECT Tumor_Type, COUNT(DISTINCT(mut.Tumor_Sample)) as sample_count '
           'FROM mutation mut '
           'GROUP BY Tumor_Type')
    df = psql.frame_query(sql, con=conn)
    df.sample_count = df.sample_count.astype(int)
    return df


def main(conn):
    out_dir = _utils.result_dir  # output directory for text files
    cfg_opts = _utils.get_output_config('sample')
    ent_opts = _utils.get_output_config('position_entropy')

    # get info about sample names
    sample_gene_cts = count_mutated_genes(conn)
    sample_mutation_cts = count_mutations(conn)
    samples_per_gene = count_per_gene(conn)
    gene_samples_per_tumor_type = gene_count_per_tumor_type(conn)
    sample_ct_per_tumor_type = count_samples_per_tumor_type(conn)
    sample_ct_per_tumor_type = sample_ct_per_tumor_type.set_index('Tumor_Type')
    sample_gene_cts.to_csv(out_dir + cfg_opts['gene_out'],
                           sep='\t', index=False)
    sample_mutation_cts.to_csv(out_dir + cfg_opts['mutation_out'],
                               sep='\t', index=False)
    samples_per_gene.to_csv(out_dir + cfg_opts['gene_sample_out'],
                            sep='\t', index=False)
    gene_samples_per_tumor_type.to_csv(out_dir + cfg_opts['tumor_type_out'],
                                       sep='\t', index=False)

    # plot results
    plot_data.sample_barplot(sample_mutation_cts,
                             _utils.plot_dir + cfg_opts['sample_barplot'],
                             title='Composition of database from size of samples',
                             xlabel='Size of sample',
                             ylabel='Number of Mutations')

    # plot kde of percent of mutations a gene is mutated
    samples_per_gene = samples_per_gene.set_index('Gene')
    pct_sample = samples_per_gene.div(float(sample_ct_per_tumor_type['sample_count'].sum()))
    pct_sample.rename(columns={'sample_count': 'sample_pct'}, inplace=True)  # columns now are percents
    plot_data.sample_kde(pct_sample,
                         _utils.plot_dir + cfg_opts['gene_pct_sample_kde'],
                         title='Percent of samples a gene is mutated',
                         xlabel='Percent of samples a gene is mutated',
                         ylabel='Density')

    # plot the max percent of samples a gene is mutated in given a tumor type
    table = pd.pivot_table(gene_samples_per_tumor_type, values='sample_count',
                           rows='Gene', cols='Tumor_Type', aggfunc=np.mean)
    table = table.div(sample_ct_per_tumor_type['sample_count'].astype(float))
    table = pd.DataFrame({'sample_pct': table.apply(np.max, axis=1)})
    table.to_csv(out_dir + cfg_opts['max_gene_pct_sample_out'], sep='\t')
    plot_data.sample_kde(table,
                         _utils.plot_dir + cfg_opts['max_gene_pct_sample_kde'],
                         title='Percent of samples a gene is mutated',
                         xlabel='Maximum percent of samples in a tumor type',
                         ylabel='Density')

    # plot the correlation between max percent of samples a gene is mutated in
    # given tumor type and the percent of maximum entropy for oncogenes
    ent_df = pd.read_csv(_utils.result_dir + ent_opts['mutation_pos_entropy'],
                         sep='\t', index_col=0)
    ent_df = ent_df[ent_df['true class']==_utils.onco_label]  # select only oncogenes
    merged_df = pd.merge(ent_df, table, how='left',
                         left_index=True, right_index=True)
    plot_data.entropy_sample_correlation(merged_df['sample_pct'],
                                         merged_df['pct of uniform mutation entropy'],
                                         _utils.plot_dir + cfg_opts['entropy_sample_correlation'])
