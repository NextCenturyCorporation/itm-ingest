import numpy as np
import pandas as pd
from os import PathLike
from typing import Optional, Iterable, List, Dict

from sklearn.neighbors import KernelDensity
from scipy.spatial.distance import jensenshannon
import math
from scipy.integrate import trapezoid

"""
NOTE: This code and scorecard.json was developed by SoarTech, https://soartech.com/ for the ITM program.
It was integrated into the ITM TA3/CACI pipeline with SoarTech's permission.
"""

def normalize_cdm_data(scores: List[np.ndarray], seed: Optional[int] = None) -> List[np.ndarray]:
    """
    Normalize scores to remove bias from the difference in the number of CDMs
    who chose each probe response.

    scores is a list of arrays of CDM responses associated with each probe.
    Each element is a n_cdm * n_calibration_probes array containing the calibration
    KDMA scores for each CDM who respnded to a probe choice.

    The process for normalization is as follows:
        - Set n to the maximum number of calibration decision makers associated with
          a probe response in a given set of responses.
        - Repeat each element of scores by a factor of n // (number of )
        - For the remainder of the above integer division, sample with replacement
          scores from the calibration decision makers until the population size
          reaches n.
    
    For example, consider 2 probe choices have the following calibration responses
    scores = [
        # scores for probe 1 choice a
        array(
            [
                [0.25, 0.3], # CDM 1 scores from calibration probes
                [0.27, 0.2]  # CDM 2 scores from calibration probes 
            ]
        ),
        # scores for probe 2 choice b
        array(
            [
                [0.15, 0.25], 
                [0.03, 0.41],
                [0.22, 0.24],
                [0.17, 0.23],
                [0.20, 0.19]
            
            ]
        )
    ]

    Since probe 1 choice a has 2 CDMs and probe 2 choice b has 5, combininig the
    responses as-is into a single KDE will bias the KDE towards choice 2b.

    To avoid this, we repeat the entries for probe 1a twice, and then draw 1 additional, 
    sample at random so that each population has 5 entries.

    scores_norm = [
        # scores for probe 1 choice a
        array(
            [
                [0.25, 0.3],
                [0.27, 0.2], 
                [0.25, 0.3],
                [0.27, 0.2],
                [0.27, 0.2],
            ]
        ),
        # scores for probe 2 choice b
        array(
            [
                [0.15, 0.25], 
                [0.03, 0.41],
                [0.22, 0.24],
                [0.17, 0.23],
                [0.20, 0.19]            
            ]
        )
    ]

    Parameters
    -----------
    scores: list[ndarray]
        list of n_CDM * n_calibration_probe arrays of calibration decision maker scores
        associated with each probe response
    
    seed: int, optional
        seed used for random sampling, if applicable.
    
    Returns
    -----------
    scores_norm: list[ndarray]
        list of n_CDM_norm * n_calibration_probe arrays with the normalized calibration
        data.
    
    """
    rng = np.random.default_rng(seed)
    # number of CDMs that picked each choice corresponding to each element
    # in scores
    n_cdms = [len(x) for x in scores]
    n_max = max(n_cdms)
    
    # each element of scores_norm is the original set of cdm responses
    # for a given probe response, repeated until the total number of CDM
    # responses is equal to lcm. Sample the remainder with replacement.
    scores_norm = [
        np.concatenate(
            [
                np.tile(scores_per_probe, (n_max // n, 1)),
                rng.choice(scores_per_probe, n_max % n, replace=True)
            ],
            axis=0
        )

        for n, scores_per_probe in zip(n_cdms, scores)
    ]
    
    return scores_norm


def _normalize(x, y):
    """
    Normalize probability distribution y such that its integral over domain x is 1.

    Parameters
    ----------
    x: ndarray
        domain over which discrete probability distribution y is defined.
    
    y: ndarray
        probability distribution at each point in x. Y is proportional to the
        probability density of the distribution at x.
    
    Returns
    --------
    pdf: ndarray
        array with same shape as y that gives normalized probability density function
        values at each point x.

    """
    # area under curve
    auc = trapezoid(y, x)

    # scale y by auc so that new area under curve is 1 --> probability density
    pdf = y / auc

    return pdf


def _kde_to_pdf(kde, x, normalize=True):
    """
    Evaluate kde over domain x and optionally normalize results into pdf.

    Parameters
    ----------
    kde: sklearn KDE model
        model used to generate distribution.

    x: ndarray
        points to evaulate kde at to generate probability function.
    
    
    Returns
    ---------
    pf: ndarray
        array containing probability function evaluated at each element in x.

    """
    pf = np.exp(kde.score_samples(x[:,np.newaxis]))

    if normalize: 
        pf = _normalize(x, pf)

    return pf


# Jensen-Shannon Divergence
def js_similarity(kde1, kde2, samples: int=100):
    # Compute the PDFs of the two KDEs at some common evaluation points
    # How likely each data point is according to the KDE model. Quantifies how well each data point fits the estimated probability distribution.
    x = np.linspace(0, 1, samples)
    pdf_kde1 = _kde_to_pdf(kde1, x)
    pdf_kde2 = _kde_to_pdf(kde2, x)
    
    # Compute the Jensen-Shannon Distance using samples
    js = jensenshannon(pdf_kde1, pdf_kde2)
    # There is a bug in the jensenshannon code, where sometimes the sqrt function gets passed a very small
    # negative number, which results in a NaN return value.
    # This error case occasionally happens when the two distributions are the same
    if js is None or math.isnan(js):
        js = 0
    # We invert the value because the spec agreed to with the other ITM performs has
    # 0 = unaligned, 1 = full aligned which is the opposite of what Jensenshannon produces. 
    return 1 - js


def get_alignments(
    responses_a: pd.DataFrame,
    responses_b: pd.DataFrame,
    scorecard_path: Optional[PathLike] = 'scorecard.json',
    scorecard: Optional[pd.DataFrame] = None,
    kdmas: Iterable[str] = (
        'MissionSuccess',
        'RiskTolerance',
        'QualityOfLife',
        'PerceivedQuantityOfLivesSaved'
    ),
    seed: Optional[int] = None
) -> Dict[str, np.float64]:
    """
    Compute alignment scores between two sets of decisions via "golden arm method".

    Takes in dataframes of decisions with the following columns:

      - "ScenarioID"
      - "ProbeID"
      - "ChoiceID"        

    With string values containing the corresponding IDs of each scenario/probe/probe choice.

    Dataframes must contain 6 rows, where each row contains a response to each probe in
    the scenario. Note probes from different scenarios cannot be mixed.
    
    
    Parameters
    -----------

    responses_a, responses_b: DataFrame, required
        Contains dataframes (in format described above) of decisions to compare.

    scorecard_path: PathLike, optional
        Default "scorecard.json"
        Path to load scorecard with calibrated scores for each probe choice.
        If None, scorecard should be passed in as a dataframe to the 'scorecard' parameter.

    scorecard: DataFrame, optional
        Dataframe containing calibrated scores for each probe choice. See pd.read_csv('scorecard.json')
        for the format/contents of the scorecard. Useful for repeated calls of this function.
    
    kdmas: iterable set of strings
        KDMAs to compute alignment results for.
        By default, all 4 kdmas from the golden arm analysis are included.

    seed: int, optional
        seed used 

    Returns
    ---------
    results: dict
        maps string KDMA names to float alignment score between responses_a and responses_b.
    """
        
    # bandwidth for KDE used in KDMA profiles
    # determined from some experimentation
    kde_bandwidth = 0.075 

    if scorecard is None:
        # contains calibrated scores for each probe response
        scorecard = pd.read_json(scorecard_path) # from calibration population
    
    scorecard['Score'] = scorecard['Score'].apply(np.asarray)

    # used for resampling probe responses with different number of calibrators in scorecard
    rng = np.random.default_rng(seed)

    # validate input dataframes
    def _validate(df):
        assert len((u := df['ScenarioID'].unique())) == 1, "Can only process results from 1 scenario"
        assert u[0].startswith('vol'),  'golden arm only applicable to VOL scenarios'
        assert len(df) == 6, "Response required for each of 6 probes in scenario"
        assert len(df['ProbeID'].unique()) == 6, "should have responses to all 6 probes in scenario"

    # get set of calibrated values for each selected probe response
    dfs = [
        df.merge(scorecard, how='inner', on=['ScenarioID','ProbeID','ChoiceID'])
        for df in (responses_a, responses_b)
    ]
    
    results = {}
    for kdma in kdmas:
        tmp = [df[df['KDMA']==kdma] for df in dfs]
        
        for df in tmp:
            _validate(df)

        # account for differences in number of calibrators per response
        scores = [normalize_cdm_data(df['Score'].values, seed=rng.integers(2**31)) for df in tmp]
        
        # aggregate all calibrated values
        scores = [np.concatenate(x).reshape(-1) for x in scores]

        # assemble into distribution-based kdma profiles
        kdes = [
            KernelDensity(kernel='gaussian', bandwidth=kde_bandwidth).fit(x.reshape(-1, 1))
            for x in scores
        ]

        # compute alignment and store
        results[kdma] = js_similarity(*kdes)
        
    # return alignments for all kdmas
    return results