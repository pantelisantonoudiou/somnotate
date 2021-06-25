# -*- coding: utf-8 -*-
"""
Created on Wed Jun  9 14:49:34 2021

@author: panton01
"""

### -------------- IMPORTS -------------- ###
import os
import pandas as pd
import numpy as np
### ------------------------------------- ###

def prepare_input_file(main_path):
    """
    Prepare .csv file for input to somnotate that will be stored under main_path

    Parameters
    ----------
    main_path : Str, Path to parent directory

    Returns
    -------
    None.

    """

    # retrieve column names from 2D lists
    path_hdrs = [x[0] for x in input_paths] # list with paths
    chnl_hdrs = [x[0] for x in input_chnls] # list with channel properties
    
    # create dataframe with column names
    df = pd.DataFrame(columns = path_hdrs + chnl_hdrs)
    
    # get edf files from raw data
    filelist = list(filter(lambda k: '.edf' in k, os.listdir(os.path.join(main_path, input_paths[1][1]))))
    filelist = [x.replace('.edf', '') for x in filelist]                
    
    for i in range(len(filelist)):
        for ii, col in enumerate(path_hdrs):
            df.at[i, col] = os.path.join(main_path, input_paths[ii][1], filelist[i]+ input_paths[ii][2])
        for ii, col in enumerate(chnl_hdrs):
            df.at[i, col] = input_chnls[ii][1]
            
    # export as csv text file 
    df.to_csv(path_or_buf = os.path.join(main_path, 'somnotate_input.csv'), index = False)


def convert_scores(load_path, save_path, file_name):
    """
    Converts sirenia sleep scores stored as text file in visBrain format (tab)

    Parameters
    ----------
    load_path : Str
    save_path : Str
    file_name : Str

    Returns
    -------
    None.

    """
    
    # get scores
    scores = pd.read_csv(os.path.join(load_path, file_name))
    
    # get sleep state transitions
    score = np.insert(scores['Score #'].to_numpy(),[len(scores)], 7) # add fake transition
    transitions = np.where(np.diff(score) != 0)[0]
    
    # get sum for each state transition
    df = scores['Score #'][transitions].reset_index()
    df = df.rename(columns={'index': 'Sum'})
    df['Sum'] *= epoch
    
    # replace values with string from dictionary
    for i in range(len(df)):
        df.at[i, 'state'] = int_to_state[df['Score #'][i]] 
    df = df.drop(['Score #'], axis=1) # drop score column
    
    # reorder columns to match visbrain
    df = df[['state', 'Sum']]
    
    # add visbrain headers
    df_hdrs = pd.DataFrame([['*Duration_sec', df['Sum'][len(df)-1]], ['*Datafile', '-']], columns = df.columns)
    df = pd.concat([df_hdrs, df])
    
    # export to txt file
    df.to_csv(path_or_buf = os.path.join(save_path, file_name), index=False, sep = '\t', header=False)
    
    
    
if __name__ == '__main__':
    
    input_paths = [
        ['file_path_sleepsign_state_annotation', 'sirenia_state_annotation', '.txt'],
        ['file_path_raw_signals', 'raw_signals', '.edf'],
        ['file_path_preprocessed_signals', 'preprocessed_signals', '.npy'],
    	['file_path_manual_state_annotation', 'manual_state_annotation', '.txt'],
    	['file_path_automated_state_annotation', 'automated_state_annotation', '.txt'],
        ['file_path_refined_state_annotation', 'refined_state_annotation', '.txt'],
        ['file_path_review_intervals', 'review_intervals', '.txt'],
    	['trained_model_file_path', 'trained_model', '.pickle'], 
        ]
    
    input_chnls = [    
        ['sampling_frequency_in_hz', 250],
        ['lfp_signal_label', 'lfp'],
    	['frontal_eeg_signal_label', 'eeg'],
    	['emg_signal_label', 'emg'],
        ]
    
    # sirenia dictionary values    
    state_to_int = dict([
        ('awake'              ,  1),
        ('awake (artefact)'   , 129),
        ('sleep movement'     ,  0),
        ('non-REM'            ,  2),
        ('non-REM (artefact)' , 130),
        ('REM'                ,  3),
        ('REM (artefact)'     , 131),
        ('undefined'          ,  255),
    ])
    
    int_to_state = {v: k for k, v in state_to_int.items()}

    
    main_path = r'C:\Users\panton01\Desktop\sleep_score' # parent directory
    epoch = 5 # time in seconds
            
    # convert sirenia scores to visbrain
    load_sirenia = os.path.join(main_path, input_paths[0][1])
    save_sirenia = os.path.join(main_path, input_paths[3][1])
    files = list(filter(lambda k: '.txt' in k, os.listdir(load_sirenia)))
    for f in files:
        convert_scores(load_sirenia, save_sirenia, f)
    print('-> Scores converted.\n')

    # generate csv file for somnotate input
    prepare_input_file(main_path)
    print('-> Input for somnotate generated.\n')

    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    


    
    


