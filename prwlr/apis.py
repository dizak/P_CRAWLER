# -*- coding: utf-8 -*-


from __future__ import print_function
import requests as rq
import pandas as pd
from tqdm import tqdm
import pathos.threading as ptth


class Columns:
    """
    Container for the columns names defined in this module.
    """
    GENOME_ID = "GENOME_ID"
    NAMES = "NAMES"
    DESCRIPTION = "DESCRIPTION"
    KEGG_ORG_ID = "KEGG_ORG_ID"
    NAME = "NAME"
    TAXON_ID = "TAXON_ID"
    KEGG_ID = "KEGG_ID"
    ORF_ID = "ORF_ID"
    ORG_GENE_ID = "ORG_GENE_ID"
    dtypes = {TAXON_ID: "uint32"}


class KEGG_API(Columns):
    """Provides connectivity with the KEGG database. Functions ending with <tbl>
    download files provided by KEGG but DO NOT modify them. Modifications
    needed for data processing are made on pandas.DataFrame.
    """
    def __init__(self):
        self.home = "http://rest.kegg.jp"
        self.operations = {"db_statistics": "info",
                           "list_entry_ids": "list",
                           "find_by_keyword": "find",
                           "get_by_entry_no": "get",
                           "conv_2_outside_ids": "conv",
                           "find_X_ref": "link"}
        self.databases = {"pathway": "path",
                          "brite": "br",
                          "module": "md",
                          "orthology": "ko",
                          "genome": "genome",
                          "genomes": "gn",
                          "genes": "genes",
                          "enzyme": "ec"}
        self.organisms_ids_df = None
        self.id_conversions = {"ncbi_gene": "ncbi-geneid",
                               "ncbi_prot": "ncbi-proteinid",
                               "uniprot": "uniprot",
                               "kegg_id": "genes"}
        self.id_conversions_df = None
        self.org_db_X_ref_df = None
        self.query_ids_found = []
        self.query_ids_not_found = []

    def get_organisms_ids(self,
                          out_file_name,
                          skip_dwnld=False):
        """Get KEGG's organisms' IDs, genomes IDs and definitions. Data are
        downloaded to a local file and then made into pandas.DataFrame. File
        can be reused. Necessary for KEGG_API.org_name_2_kegg_id.

        Args:
            out_file_name (str): name for file to be downloaded
            skip_dwnld (bool): read existing file when <True>. Default <False>
        """
        if skip_dwnld is True:
            pass
        else:
            url = "{0}/{1}/{2}".format(self.home,
                                       self.operations["list_entry_ids"],
                                       self.databases["genome"])
            res = rq.get(url)
            with open(out_file_name, "wb") as fout:
                fout.write(res.content)
        self.organisms_ids_df = pd.read_csv(out_file_name,
                                            names=[self.GENOME_ID,
                                                   self.NAMES,
                                                   self.DESCRIPTION],
                                            header=None,
                                            sep="\t|;",
                                            engine="python",
                                            error_bad_lines=False,
                                            warn_bad_lines=True)
        temp_sub_df = self.organisms_ids_df[self.NAMES].str.split(",", expand=True)
        temp_sub_df.columns = [self.KEGG_ORG_ID, self.NAME, self.TAXON_ID]
        self.organisms_ids_df.drop(self.NAMES, axis=1, inplace=True)
        self.organisms_ids_df = pd.concat([self.organisms_ids_df, temp_sub_df], axis=1)
        self.organisms_ids_df.replace({"genome:": ""},
                                      regex=True,
                                      inplace=True)
        self.organisms_ids_df.dropna(inplace=True)
        self.organisms_ids_df = self.organisms_ids_df.astype({k: v for k, v in self.dtypes.items()
                                                              if k in self.organisms_ids_df.columns})

    def org_name_2_kegg_id(self,
                           organism,
                           assume_1st=True):
        """Return KEGG's organisms' IDs (str) when queried  with a regular
        (natural) biological name. Case-sensitive. Uses KEGG_API.organisms_ids_df
        generated by KEGG_API.get_organisms_ids. Necessary for creation of ids
        list which is then passed to Genome.KO_list_profiler.

        Args:
            organism (str): biological organism's name to query against
            the KEGG's IDs
            assume_1st (bool): return the first item if more than one hit when
            <True> (default)
        """
        org_bool = self.organisms_ids_df[self.DESCRIPTION].str.contains(organism)
        organism_ser = self.organisms_ids_df[org_bool]
        if len(organism_ser) == 0:
            print("No record found for {}".format(organism))
            self.query_ids_not_found.append(organism)
        elif len(organism_ser) > 1:
            print("More than one record for this query\n{}".format(organism_ser[[self.DESCRIPTION,
                                                                                 self.KEGG_ORG_ID]]))
            if assume_1st is True:
                self.query_ids_found.append(organism)
                return organism_ser[self.KEGG_ORG_ID].iloc[0]
            else:
                return None
        else:
            self.query_ids_found.append(organism)
            return organism_ser[self.KEGG_ORG_ID].iloc[0]

    def get_org_db_X_ref(self,
                         organism,
                         target_db,
                         out_file_name,
                         skip_dwnld=False,
                         strip_prefix=True,
                         drop_duplicates=True):
        """Get desired KEGG's database entries linked with all the genes from
        given organism. Data are downloaded to a local file and then made into
        pandas.DataFrame. File can be reused. Necessary for
        KEGG_API.get_ortho_db_entries and Ortho_Interactions.KO_based_appender.

        Args:
            organism (str): organism name. Provide whitespace-separated full
            species name. Uses pandas.series.str.contains method.
            targed_db (str): dict key for KEGG_API.databases of desired
            database.
            out_file_name (str): name for file to be downloaded
            skip_dwnld (bool) = read existing file when <True>. Default <False>
        """
        org_id = self.org_name_2_kegg_id(organism)
        if skip_dwnld is True:
            pass
        else:
            url = "{0}/{1}/{2}/{3}".format(self.home,
                                           self.operations["find_X_ref"],
                                           self.databases[target_db],
                                           org_id)
            res = rq.get(url)
            with open(out_file_name, "wb") as fout:
                fout.write(res.content)
        self.org_db_X_ref_df = pd.read_csv(out_file_name,
                                           names=[self.ORF_ID, self.KEGG_ID],
                                           header=None,
                                           sep="\t")
        if strip_prefix is True:
            self.org_db_X_ref_df.replace({"{}:".format(org_id): "",
                                          "{}:".format(self.databases[target_db]): ""},
                                         regex=True,
                                         inplace=True)
        if drop_duplicates:
            self.org_db_X_ref_df.drop_duplicates(
                subset=[self.ORF_ID],
                keep=False,
                inplace=True,
            )
            self.org_db_X_ref_df.drop_duplicates(
                subset=[self.KEGG_ID],
                keep=False,
                inplace=True,
            )

    def get_KOs_db_X_ref(self,
                         filename,
                         target_db='genes',
                         skip_dwnld=False,
                         strip_prefix=True,
                         squeeze=True,
                         sep="\t",
                         threads=1):
        """
        Get desired KEGG's database entries linked with KEGG Orthology Group.
        Data are downloaded to a local file and then made into pandas.DataFrame.
        File can be reused.

        Parameters
        -------
        filename: str
            Name of the file to download.
        targed_db: str
            Key for KEGG_API.databases of desired database.
        skip_dwnld: bool, default <False>
            Read already downloaded file if <True>
        squeeze: bool, default <True>
            Compress list of the organisms to list for each KEGG Orthology
            Group
        sep: str, default: <\t>
            Delimiter to use.
        threads: int, default <1>
            Number of threads to spawn during download.

        Uses
        -------
        KEGG_API.org_db_X_ref_df: pandas.DataFrame
            Source of the KEGG Orthology Groups.

        Sets
        -------
        KEGG_API.KOs_db_X_ref_df: pandas.DataFrame
            DataFrame of KEGG Orthology Group ID and belonging organisms and
            genes
        """
        def f(i):
            print("{} ".format(i), flush=True, end='\r')
            res = rq.get('{}/{}/{}/{}'.format(
            self.home,
            self.operations['find_X_ref'],
            self.databases[target_db],
            i,
            ))
            with open(filename, 'ab') as fout:
                fout.write(res.content)
        if not skip_dwnld:
            if threads > 1:
                ptth.ThreadPool(threads).map(
                    f,
                    self.org_db_X_ref_df[self.KEGG_ID]
                )
            else:
                map(f, self.org_db_X_ref_df[self.KEGG_ID])
        self.KOs_db_X_ref_df = pd.read_csv(filename,
                                           names=[self.KEGG_ID,
                                                  self.ORG_GENE_ID],
                                           header=None,
                                           sep=sep)
        if strip_prefix:
            self.KOs_db_X_ref_df.replace({"{}:".format(self.databases["orthology"]): ""},
                                         regex=True,
                                         inplace=True)
            self.KOs_db_X_ref_df.replace({":.+": ""},
                                         regex=True,
                                         inplace=True)
        if squeeze:
            self.KOs_db_X_ref_df = self.KOs_db_X_ref_df.groupby(
                by=[self.KEGG_ID]
                )[self.ORG_GENE_ID].apply(list).to_frame().reset_index()

    def get_db_entries(self,
                       out_file_name):
        """Get full database by quering entries from
        KEGG_API.org_db_X_ref_df and download them into a local file.
        Necessary for Genome.parse_KO_db. The only func that does NOT convert
        downloaded file into pandas.DataFrame. Uses KEGG_API.get_db_X_ref_df.

        Args:
            out_file_name (str): name for file to be downloaded
        """
        entries = self.org_db_X_ref_df[self.KEGG_ID].drop_duplicates()
        for i in tqdm(entries):
            url = "{0}/{1}/{2}".format(self.home,
                                       self.operations["get_by_entry_no"],
                                       i)
            res = rq.get(url)
            with open(out_file_name, "ab") as fout:
                fout.write(res.content)


class CostanzoAPI:
    """Provides connectivity with the Costanzo's SOM website of the Genetic
    Landscape of the Cell project, allowing data files download.

    Attribs:
        home (str): Costanzo's SOM home page address
        raw (str): raw data link and file name
        raw_matrix (str): raw data genetic interactions matrix link and file
        name, Java Treeview format
        lenient_cutoff (str): GIS_P < 0.05 cutoff link and file name
        intermediate_cutoff (str): |genetic interaction score| > 0.08,
        GIS_P < 0.05 cutoff link and file name
        stringent_cutoff (str): genetic interaction score < -0.12,
        GIS_P < 0.05 or genetic interaction score > 0.16, GIS_P < 0.05 link
        and file name
        bioprocesses (str): bioprocesses annotations
        chemical_genomics (str): chemical genomics data
        query_list (str): query ORFs list
        array_list (str): array ORFs list
    """

    def __init__(self):
        self.home = {"v1": "http://drygin.ccbr.utoronto.ca/~costanzo2009",
                     "v2": "http://thecellmap.org/costanzo2016/"}
        self.data = {"v1": {"raw": "sgadata_costanzo2009_rawdata_101120.txt.gz",
                            "raw_matrix": "sgadata_costanzo2009_rawdata_matrix_101120.txt.gz",
                            "lenient_cutoff": "sgadata_costanzo2009_lenientCutoff_101120.txt.gz",
                            "intermediate_cutoff": "sgadata_costanzo2009_intermediateCutoff_101120.txt.gz",
                            "stringent_cutoff": "sgadata_costanzo2009_stringentCutoff_101120.txt.gz",
                            "bioprocesses": "bioprocess_annotations_costanzo2009.xls",
                            "chemical_genomics": "chemgenomic_data_costanzo2009.xls",
                            "query_list": "sgadata_costanzo2009_query_list_101120.txt",
                            "array_list": "sgadata_costanzo2009_array_list.txt"},
                       "v2": {"pairwise": "data_files/Raw%20genetic%20interaction%20datasets:%20Pair-wise%20interaction%20format.zip",
                              "matrix": "data_files/Raw%20genetic%20interaction%20datasets:%20Matrix%20format.zip",
                              "interaction_profile_similarity_matrices": "data_files/Genetic%20interaction%20profile%20similarity%20matrices.zip"}}

    def get_data(self,
                 data,
                 output_directory=".",
                 sga_version="v2"):
        """Get files from Costanzo's SOM website.

        Args:
            data (str): specifies the file to be downloaded.
            <raw> for raw dataset,
            <raw_matrix> for raw genetic interactions matrix,
            <lenient_cutoff> for lenient dataset,
            <intermediate_cutoff> for intermediate dataset,
            <stringent_cutoff> for stringent dataset,
            <bioprocesses> for bioprocesses dataset,
            <chemical_genomics> for chemical genomics dataset,
            <query_list> for list of query ORFs names,
            <array_list> for list of array ORFs names
            out_file_name (str): name for file to be downloaded. Automatically
            same as appropriate Costanzo_API attrib when set to <None>
        """
        if data not in list(self.data[sga_version].keys()):
            raise ValueError("unknown option for data arg")
        url = "{0}/{1}".format(self.home[sga_version],
                               self.data[sga_version][data])
        out_file_name = self.data[sga_version][data].replace("data_files/", "").replace("%20", "_").replace(":", "-")
        res = rq.get(url)
        with open("{}/{}".format(output_directory, out_file_name), "wb") as fout:
            fout.write(res.content)