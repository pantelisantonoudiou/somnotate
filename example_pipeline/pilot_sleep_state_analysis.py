# -*- coding: utf-8 -*-

import os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
sns.set(font_scale=2)
sns.set_style("whitegrid")
# =============================================================================
#                               Somnotate Functions
# =============================================================================

# state_to_int = dict([
#     ('awake'              ,  1),
#     # ('awake (artefact)'   , -1),
#     # ('sleep movement'     ,  1),
#     ('non-REM'            ,  2),
#     # ('non-REM (artefact)' , -2),
#     ('REM'                ,  3),
#     # ('REM (artefact)'     , -3),
#     # ('undefined'          ,  0),
# ])

def load_hypnogram(file_path):
    """
    Load hypnogram given in visbrain Stage-duration format.

    Arguments:
    ----------
    file_path -- str
        /path/to/hypnogram/file.hyp

    Returns:
    --------
    states -- list of str
        List of annotated states.

    intervals -- list of (float start, float stop) tuples
        Corresponding time intervals.

    References:
    -----------
    http://visbrain.org/sleep.html#save-hypnogram
    """
    dtype = [('Stage', '|S30'), ('stop', float)]
    data = np.genfromtxt(file_path, skip_header=2, dtype=dtype, delimiter='\t')
    states = [state.astype(str).strip() for state in data['Stage']]
    transitions = np.r_[0, data['stop']]
    intervals = list(zip(transitions[:-1], transitions[1:]))
    return states, intervals

def convert_state_intervals_to_state_vector(states, intervals, mapping,
                                            time_resolution = 1.,
                                            length          = None,
):
    """
    Construct a state vector given a list of states and a corresponding list of intervals.

    Arguments:
    ----------
    states -- list of ints (or str if mapping is not None)
        The state vector.

    intervals -- list of (float start, float stop) tuples
        The contiguous intervals corresponding to each state in the state vector.

    mapping -- dict str : int
        The mapping from states in the state vector to integers.

    time_resolution -- float (default 1.)
       The assumed time duration of each entry in the state vector.

    Returns:
    --------
    state_vector -- (total samples, ) ndarray with dtype int
        The state vector.

    See also:
    ---------
    convert_state_vector_to_state_intervals
    """

    if time_resolution != 1:
        intervals = [(start/time_resolution, stop/time_resolution) for start, stop in intervals]

    if np.any([(isinstance(start, float), isinstance(stop, float)) for start, stop in intervals]):
        # breakpoint()
        # import warnings
        # warnings.warn("Interval values are converted from floats to integers.")
        # # round up last interval such that the state vector is guaranteed to include the last time point
        # last_start, last_stop = intervals[-1]
        # intervals[-1] = (last_start, np.ceil(last_stop))
        intervals = [(int(np.round(start)), int(np.round(stop))) for start, stop in intervals]

    if not length:
        length = np.max(intervals)

    state_vector = np.zeros((length), dtype=int)
    for state, (start, stop) in zip(states, intervals):
        state_vector[start:stop] = mapping[state]

    return state_vector

# =============================================================================
# =============================================================================

# plotting function
def get_color_for_stage(stage):
    color_mapping = {
        'awake': 'blue',       # Awake
        'non-REM': 'green',    # non-REM
        'REM': 'red'           # REM
    }
    return color_mapping.get(stage, 'black')

if __name__ == '__main__':
    
    # create index csv
    # files = [x for x in os.listdir(path) if x[-3:] =='hyp']
    # index = pd.DataFrame({'file':files})
    # index['stress'] = 'cus'
    # index.loc[index['file'].str.contains('pre'), 'stress'] = 'baseline'
    # index['treatment'] = 'control'
    # index.loc[index['file'].str.contains('SAGE|SGE|147'), 'treatment'] = 'sage_516'
    # index = index.reset_index().rename(columns={'index':'animal_id'})
    
    # settings
    state_to_int = dict([
        ('awake'              ,  1),
        ('non-REM'            ,  2),
        ('REM'                ,  3),
    ])
    
    # path and index
    path = r'D:\sleep_scoring\cus_files\processed'
    index = pd.read_csv(r"D:\sleep_scoring\cus_files\index.csv")

    # get hypnograms and conditions in dataframes
    cols = ['file_id','animal_id', 'stress', 'treatment']
    int_to_state = {v: k for k, v in state_to_int.items()}
    data_list = []
    state_dict= {}
    total_time_dict = {}
    for i, row in index.iterrows():
        # load hypnogram and convert to sleep state vector
        states, intervals = load_hypnogram(os.path.join(path, row['file']))
        state_vector = convert_state_intervals_to_state_vector(states, intervals, time_resolution=1, mapping=state_to_int)
        
        # add vector for each animal to dataframe
        df_temp = pd.DataFrame({'time_sec': np.arange(len(state_vector)),
                           'sleep_state': state_vector})
        df_temp['sleep_stage'] = df_temp['sleep_state'].map(int_to_state)
        df_temp[cols] = row[cols]
        data_list.append(df_temp)
        state_dict.update({row.file_id:states})
        total_time_dict.update({row.file_id:len(state_vector)})
    data = pd.concat(data_list).reset_index(drop=True)

    # 1a) plot percent time in each sleep state
    sleep_df = data.groupby(cols + ['sleep_stage'])['time_sec'].count().reset_index()
    sleep_df['total_time'] = sleep_df.groupby('file_id')['time_sec'].transform('sum')
    sleep_df['percent_time'] = 100 * sleep_df['time_sec'] / sleep_df['total_time']
    sns.catplot(data=sleep_df, hue='treatment', y='percent_time', x='stress',
                col='sleep_stage', kind='bar', errorbar='se', height=6,
                hue_order=['control', 'sage_516'], palette=['#76deaf', '#bd64e3'], )
    
    # 1b) normalize to baseline
    norm_df_list = []
    var_name = '% Change in Sleep Occupancy (cus / base)'
    for (animal_id, sleep_stage), df in sleep_df.groupby(['animal_id', 'sleep_stage']):
        if len(df) == 2:
            base = df[df['stress'] == 'baseline']['percent_time'].values[0]
            cus = df[df['stress'] == 'cus']['percent_time'].values[0]
            temp_dict = {var_name: 100*cus/base, 
                         'animal_id':animal_id,
                         'sleep_stage': sleep_stage,
                         'treatment': df['treatment'].values[0]}
            norm_df_list.append(temp_dict)
    norm_df = pd.DataFrame(norm_df_list)
    g = sns.catplot(data=norm_df, y=var_name, x='treatment', col='sleep_stage',
                kind='bar', errorbar='se', height=7, palette=['#76deaf', '#bd64e3'],
                order=['control', 'sage_516'])
    for ax in g.axes.flatten():
        ax.axhline(y=100, ls='--', color='grey', linewidth=2)
    plt.tight_layout()
    
    # 2a) bout duration
    data['state_change'] = (data['sleep_stage'] != data['sleep_stage'].shift()).cumsum()
    data['bout_duration'] = data.groupby(['file_id', 'state_change']).cumcount() + 1
    bout_length_df = data.groupby(cols+['sleep_stage', 'state_change'])['bout_duration'].max().reset_index()
    bout_length_df = bout_length_df.groupby(['animal_id','sleep_stage', 'treatment', 'stress'])['bout_duration'].mean().reset_index()
    sns.catplot(data=bout_length_df, hue='treatment', y='bout_duration', x='stress',
                col='sleep_stage', kind='bar', errorbar='se', height=6,
                hue_order=['control', 'sage_516'], palette=['#76deaf', '#bd64e3'], )

    # 2b) normalize to baseline
    norm_df_list = []
    var_name = '% Change in bout duration (cus / base)'
    for (animal_id, sleep_stage), df in bout_length_df.groupby(['animal_id', 'sleep_stage']):
        if len(df) == 2:
            base = df[df['stress'] == 'baseline']['bout_duration'].values[0]
            cus = df[df['stress'] == 'cus']['bout_duration'].values[0]
            temp_dict = {var_name: 100*cus/base, 
                         'animal_id':animal_id,
                         'sleep_stage': sleep_stage,
                         'treatment': df['treatment'].values[0]}
            norm_df_list.append(temp_dict)
    norm_df = pd.DataFrame(norm_df_list)
    g = sns.catplot(data=norm_df, y=var_name, x='treatment', col='sleep_stage',
                kind='bar', errorbar='se', height=7, palette=['#76deaf', '#bd64e3'],
                order=['control', 'sage_516'])
    for ax in g.axes.flatten():
        ax.axhline(y=100, ls='--', color='grey', linewidth=2)
    plt.tight_layout()
    
    # 3a) number of bouts
    bout_df_list = []
    for animal_id in state_dict:
        df = pd.DataFrame({'sleep_stage':state_dict[animal_id]})
        df['file_id'] = animal_id
        df['time_sec'] = total_time_dict[animal_id]
        bout_df_list.append(df)
    bout_df = pd.concat(bout_df_list).reset_index(drop=True)
    bout_df = pd.merge(index, bout_df, on='file_id', how='outer')
    bout_df = bout_df.groupby(['animal_id', 'sleep_stage', 'treatment', 'stress']).agg(
    bout_number=('file', 'count'), total_time_sec=('time_sec', 'mean')).reset_index()
    bout_df['bout_frequency'] = bout_df['bout_number'] / bout_df['total_time_sec']
    sns.catplot(data=bout_df, hue='treatment', y='bout_frequency', x='stress',
                col='sleep_stage', kind='bar', errorbar='se', height=6,
                hue_order=['control', 'sage_516'], palette=['#76deaf', '#bd64e3'], )

    # 3b) normalize to baseline
    norm_df_list = []
    var_name = '% Change in bout frequency (cus / base)'
    for (animal_id, sleep_stage), df in bout_df.groupby(['animal_id', 'sleep_stage']):
        if len(df) == 2:
            base = df[df['stress'] == 'baseline']['bout_frequency'].values[0]
            cus = df[df['stress'] == 'cus']['bout_frequency'].values[0]
            temp_dict = {var_name: 100*cus/base, 
                         'animal_id':animal_id,
                         'sleep_stage': sleep_stage,
                         'treatment': df['treatment'].values[0]}
            norm_df_list.append(temp_dict)
    norm_df = pd.DataFrame(norm_df_list)
    g = sns.catplot(data=norm_df, y=var_name, x='treatment', col='sleep_stage',
                kind='bar', errorbar='se', height=7, palette=['#76deaf', '#bd64e3'],
                order=['control', 'sage_516'])
    for ax in g.axes.flatten():
        ax.axhline(y=100, ls='--', color='grey', linewidth=2)
    plt.tight_layout()

    # count transitions # TODO # Need to finalize (normalize transition number by file length) # first get histogram and then normalize by file length
    transition_list = []
    for file_id in state_dict:
        transitions = state_dict[file_id]
        pairs = [f'{transitions[i]} -> {transitions[i + 1]}' for i in range(len(transitions) - 1)]
        df = pd.DataFrame({'transition_pair':pairs})
        df = pd.DataFrame(df['transition_pair'].value_counts()/df['transition_pair'].value_counts().sum()).reset_index()
        df = df.rename(columns={'transition_pair':'transition_probability'}).rename(columns={'index':'transition_pair'})
        df['file_id'] = file_id
        transition_list.append(df)
    transition_df = pd.concat(transition_list).reset_index(drop=True)
    transition_df = pd.merge(index, transition_df, on='file_id', how='outer')
    g = sns.catplot(data=transition_df, x='transition_pair', y='transition_probability', hue='stress', kind='bar', errorbar='se',
                col='treatment', hue_order=['baseline', 'cus'], palette=['#878787', '#f2ae5a'], height=10)
    for ax in g.axes.flat: 
        ax.set_xticklabels(ax.get_xticklabels(), rotation=45)
    plt.tight_layout()

    



