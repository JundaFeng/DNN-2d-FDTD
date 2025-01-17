from abc import ABC

import torch
import torch.nn as nn
from torch.autograd import Variable
import parameters as param
param = param.parameter()

class ConvLSTMCell(nn.Module):

    def __init__(self, input_dim, hidden_dim, kernel_size, bias):
        """
        Initialize ConvLSTM cell.

        Parameters
        ----------
        input_dim: int
            Number of channels of input tensor.
        hidden_dim: int
            Number of channels of hidden state.
        kernel_size: (int, int)
            Size of the convolutional kernel.
        bias: bool
            Whether or not to add the bias.
        """

        super(ConvLSTMCell, self).__init__()

        self.input_dim = input_dim
        self.hidden_dim = hidden_dim

        self.kernel_size = kernel_size
        self.padding = kernel_size[0] // 2, kernel_size[1] // 2
        self.bias = False*bias

        self.conv = nn.Conv2d(in_channels=self.input_dim + self.hidden_dim,
                              out_channels=4 * self.hidden_dim,
                              kernel_size=self.kernel_size,
                              stride=(1, 1),
                              padding=self.padding,
                              bias=self.bias)

    def forward(self, input_tensor, cur_state):
        h_cur, c_cur = cur_state

        combined = torch.cat([input_tensor, h_cur], dim=1)  # concatenate along channel axis

        combined_conv = self.conv(combined)
        cc_i, cc_f, cc_o, cc_g = torch.split(combined_conv, self.hidden_dim, dim=1)
        i = torch.sigmoid(cc_i)
        f = torch.sigmoid(cc_f)
        o = torch.sigmoid(cc_o)
        g = torch.tanh(cc_g)

        c_next = f * c_cur + i * g
        h_next = o * torch.tanh(c_next)

        return h_next, c_next

    def init_hidden(self, batch_size, shape):
        height, width = shape
        return (torch.zeros(batch_size, self.hidden_dim, height, width, device=self.conv.weight.device),
                torch.zeros(batch_size, self.hidden_dim, height, width, device=self.conv.weight.device))

class EncoderDecoderConvLSTM(nn.Module):
    def __init__(self, nf, in_chan):
        """
            ARCHITECTURE:
            Encoder (ConvLSTM)
            Encoder Vector (final hidden state of encoder)
            Decoder (ConvLSTM) - takes Encoder Vector as input
            Decoder (3D CNN) - produces regression predictions for our model
        """
        super(EncoderDecoderConvLSTM, self).__init__()

        self.encoder_1_convlstm = ConvLSTMCell(input_dim=in_chan,
                                               hidden_dim=nf,
                                               kernel_size=(3, 3),
                                               bias=True)

        self.encoder_2_convlstm = ConvLSTMCell(input_dim=nf,
                                               hidden_dim=nf,
                                               kernel_size=(3, 3),
                                               bias=True)

        self.encoder_3_convlstm = ConvLSTMCell(input_dim=nf,
                                               hidden_dim=nf,
                                               kernel_size=(3, 3),
                                               bias=True)


        self.decoder_1_convlstm = ConvLSTMCell(input_dim=nf,  # nf + 1
                                               hidden_dim=nf,
                                               kernel_size=(3, 3),
                                               bias=True)


        self.decoder_2_convlstm = ConvLSTMCell(input_dim=nf,
                                               hidden_dim=nf,
                                               kernel_size=(3, 3),
                                               bias=True)

        self.decoder_3_convlstm = ConvLSTMCell(input_dim=nf,
                                               hidden_dim=nf,
                                               kernel_size=(3, 3),
                                               bias=True)

        self.decoder_CNN = nn.Conv3d(in_channels=nf,
                                     out_channels=1,
                                     kernel_size=(1, 3, 3),
                                     padding=(0, 1, 1))


    def autoencoder(self, x, seq_len, future_step, h_t, c_t, h_t3, c_t3): # h_t2, c_t2,  #, h_t4, c_t4,     h_t5, c_t5,h_t6, c_t6):
        outputs = []
        # encoder
        for t in range(seq_len):
            h_t, c_t = self.encoder_1_convlstm(input_tensor=x[:, t, :, :],
                                               cur_state=[h_t, c_t])  # we could concat to provide skip conn here
            #h_t2, c_t2 = self.encoder_2_convlstm(input_tensor=h_t,
            #                                     cur_state=[h_t2, c_t2])  # we could concat to provide skip conn here
            #h_t5, c_t5 = self.encoder_2_convlstm(input_tensor=h_t2,
            #                                     cur_state=[h_t5, c_t5])

        # encoder_vector
        encoder_vector = h_t  # h_t2

        # decoder
        for t in range(future_step):
            h_t3, c_t3 = self.decoder_1_convlstm(input_tensor=encoder_vector,
                                                 cur_state=[h_t3, c_t3])  # we could concat to provide skip conn here
            #h_t4, c_t4 = self.decoder_2_convlstm(input_tensor=h_t3,
            #                                     cur_state=[h_t4, c_t4])  # we could concat to provide skip conn here
            #h_t6, c_t6 = self.decoder_2_convlstm(input_tensor=h_t4,
            #                                     cur_state=[h_t6, c_t6])
            encoder_vector = h_t3  # h_t4
            outputs += [h_t3]# [h_t4]  # predictions

        outputs = torch.stack(outputs, 1)
        outputs = outputs.permute(0, 2, 1, 3, 4)
        outputs = self.decoder_CNN(outputs)
        outputs = torch.nn.Sigmoid()(outputs)
        return outputs

    def forward(self, x, future_seq=param.opt.n_future_seq, hidden_state=None):
        """
            Parameters
            ----------
            input_tensor:
                5-D Tensor of shape (b, t, c, h, w)        #   batch, time, channel, height, width
        """
        # find size of different input dimensions
        b, seq_len, _, h, w = x.size()
        # initialize hidden states
        h_t, c_t = self.encoder_1_convlstm.init_hidden(batch_size=b,  shape=(h, w))
        #h_t2, c_t2 = self.encoder_2_convlstm.init_hidden(batch_size=b, shape=(h, w))
        h_t3, c_t3 = self.decoder_1_convlstm.init_hidden(batch_size=b, shape=(h, w))
        #h_t4, c_t4 = self.decoder_2_convlstm.init_hidden(batch_size=b, shape=(h, w))
        #h_t5, c_t5 = self.encoder_1_convlstm.init_hidden(batch_size=b,  shape=(h, w))
        #h_t6, c_t6 = self.decoder_2_convlstm.init_hidden(batch_size=b, shape=(h, w))
        # autoencoder forward, 网络结构越浅越好 ？
        outputs = self.autoencoder(x, seq_len, future_seq, h_t, c_t, h_t3, c_t3)  #, h_t4, c_t4,    h_t5, c_t5, h_t6, c_t6)
        return outputs



