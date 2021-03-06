import os
import numpy as np
import sys
import time
import argparse
import torch
import matplotlib.pyplot as plt
from scipy.io.wavfile import write
from hparams import create_hparams
from model import Tacotron2
from text import text_to_sequence
sys.path.append('waveglow/')
from waveglow.mel2samp import MAX_WAV_VALUE
from denoiser import Denoiser
import json

class T2S:
    def __init__(self, lang):
        self.language = lang
        self.hparams = create_hparams()
        self.hparams.sampling_rate = 22050
        with open('config.json', 'r') as f:
            self.config = json.load(f)

        self.waveglow_path = self.config.get('model').get('waveglow')
        self.waveglow = torch.load(self.waveglow_path)['model']
        self.waveglow.cuda().eval().half()

        for m in self.waveglow.modules():
            if 'Conv' in str(type(m)):
                setattr(m, 'padding_mode', 'zeros')
                
        for k in self.waveglow.convinv:
            k.float()
        self.denoiser = Denoiser(self.waveglow)
        self.update_model(lang)

    
    def load_model(self):
        model = Tacotron2(self.hparams).cuda()
        if self.hparams.fp16_run:
            model.decoder.attention_layer.score_mask_value = finfo('float16').min

        if self.hparams.distributed_run:
            model = apply_gradient_allreduce(model)

        return model

    def tts(self, text, filename=None):
        if not filename:
            filename = str(time.time())
        sequence = np.array(text_to_sequence(text, [self.cleaner]))[None, :]
        sequence = torch.autograd.Variable(torch.from_numpy(sequence)).cuda().long()
        mel_outputs, mel, _, alignments = self.model.inference(sequence)
        
        with torch.no_grad():
            audio = self.waveglow.infer(mel, sigma=0.666)
            audio = audio * MAX_WAV_VALUE
        # audio = self.denoiser(audio, strength=0.01)[:, 0]
        audio = audio.squeeze()
        audio = audio.cpu().numpy()
        audio = audio.astype('int16')
        audio_path =f"{filename}.wav"
        save_path = os.path.join('wavs',audio_path)
        write(save_path, self.hparams.sampling_rate, audio)
        print("audio saved at: {}".format(save_path))
        return audio_path
        
        

    def update_model(self, lang):
        if lang == 'en':
            self.checkpoint_path = self.config.get('model').get('en')
            self.cleaner = 'english_cleaners'
            self.language = lang
        else:
            self.checkpoint_path = self.config.get('model').get('kr')
            self.cleaner =  'transliteration_cleaners'
            self.language = lang

        self.model = self.load_model()
        self.model.load_state_dict(torch.load(self.checkpoint_path)['state_dict'])
        _ = self.model.cuda().eval().half()
        return self

        
        

