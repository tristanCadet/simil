# load_rt_polarity_dataset
import os
import numpy as np
from sklearn.model_selection import train_test_split

# ngram_vectorize
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.feature_selection import SelectKBest, f_classif

# mlp_model
from tensorflow.python.keras import models
from tensorflow.python.keras.layers import Dense, Dropout

# checkLabels
import explore_data

# train_ngram_model
import tensorflow as tf

from collections import defaultdict

def load_rt_polarity_dataset(data_path = "datasets", seed=123, test_split=0.2):
    """Loads the rt-polarity dataset.

    # Arguments
        data_path: string, path to the data directory.
        seed: int, seed for randomizer.
        test_split: float, proportion of test samples.

    # Returns
        A tuple of training and test data.
        Number of samples: 10662
        Number of categories: 2 (0 - negative, 1 - positive)

    # References
        Bo Pang and Lillian Lee, 'Seeing stars: Exploiting class relationships for sentiment categorization with respect to rating scales.', Proceedings of the ACL, 2005.

        Download and uncompress archive from:
        http://www.cs.cornell.edu/people/pabo/movie-review-data/rt-polarydata.tar.gz
    """
    rt_path = os.path.join(data_path, 'rt-polaritydata', 'rt-polaritydata')
    pos_path = os.path.join(rt_path, 'rt-polarity.pos')
    neg_path = os.path.join(rt_path, 'rt-polarity.neg')

    with open(pos_path, encoding="latin-1") as pos_f, open(neg_path, encoding="latin-1") as neg_f:
        pos_data = pos_f.readlines()
        neg_data = neg_f.readlines()
    assert len(pos_data)==len(neg_data)

    data = pos_data + neg_data
    labels = [1]*len(pos_data) + [0]*len(neg_data)

    return train_test_split(data, np.array(labels), random_state=seed, test_size=test_split)

def ngram_vectorize(train_texts, train_labels, test_texts, ngram_range=(1,2), top_k=20000, token_mode='word', min_doc_freq=2):
    """Vectorizes texts as n-gram vectors.

    1 text = 1 tf-idf vector the length of vocabulary of unigrams + bigrams.

    # Arguments
        train_texts: list, training text strings.
        train_labels: np.ndarray, training labels.
        test_texts: list, test text strings.
        ngram_range: tuple, range (inclusive) of n-gram sizes for tokenizing text.
        top_k: int, limit on the number of features.
        token_mode: string, whether text should be split into word or character n-grams. One of 'word', 'char'.
        min_doc_freq: int, minimum document/corpus frequency below which a token will be discarded.

    # Returns
        x_train, x_test: vectorized training and test texts
    """
    # Create keyword arguments to pass to the 'tf-idf' vectorizer.
    kwargs = {
            'ngram_range': ngram_range,
            'dtype': 'int32',
            'strip_accents': 'unicode',
            'decode_error': 'replace',
            'analyzer': token_mode,
            'min_df': min_doc_freq,
    }
    vectorizer = TfidfVectorizer(**kwargs)

    # Learn vocabulary from training texts and vectorize training texts.
    x_train = vectorizer.fit_transform(train_texts)

    # Vectorize test texts.
    x_test = vectorizer.transform(test_texts)

    # Select top 'k' of the vectorized features.
    selector = SelectKBest(f_classif, k=min(top_k, x_train.shape[1]))
    selector.fit(x_train, train_labels)
    x_train = selector.transform(x_train).astype('float32')
    x_test = selector.transform(x_test).astype('float32')
    return x_train, x_test, vectorizer, selector

def mlp_model(units, input_shape, num_classes = 2, dropout_rate = 0.2, activation='relu', optimizer='rmsprop', regularizer=None):
    """Creates an instance of a multi-layer perceptron model.

    # Arguments
        units: int array, output dimension for each of the layers.
        input_shape: tuple, shape of input to the model.
        num_classes: int, number of output classes.
        dropout_rate: float, percentage of input to drop at Dropout layers.
        activation: string, the activation function.

    # Returns
        An MLP model instance.
    """
    model = models.Sequential()
    model.add(Dropout(rate=dropout_rate, input_shape=input_shape))

    for dim in units:
        model.add(Dense(units=dim, activation=activation, kernel_regularizer=regularizer))
        model.add(Dropout(rate=dropout_rate))

    op_units, op_activation, loss = (1, 'sigmoid', 'binary_crossentropy') if num_classes==2 else (num_classes, 'softmax', 'sparse_categorical_crossentropy')

    model.add(Dense(units=op_units, activation=op_activation))
    model.compile(optimizer=optimizer, loss=loss, metrics=['acc'])
    return model

def checkLabels(train_labels, test_labels):
    # Verify that validation labels are in the same range as training labels.
    num_classes = explore_data.get_num_classes(train_labels)
    unexpected_labels = [v for v in test_labels if v not in range(num_classes)]
    if len(unexpected_labels):
        raise ValueError('Unexpected label values found in the validation set:'
                         ' {unexpected_labels}. Please make sure that the '
                         'labels in the validation set are in the same range '
                         'as training labels.'.format(unexpected_labels=unexpected_labels))
    return num_classes

def train_model(model, x_train, train_labels, epochs=1000, val_split=0.2, batch_size=32, filename='rt_mlp_model'):

    callbacks = [tf.keras.callbacks.EarlyStopping(monitor='val_acc', patience=1)]

    # Train and validate model.
    history = model.fit(
            x_train,
            train_labels,
            epochs=epochs,
            callbacks=callbacks,
            validation_split=val_split,
            verbose=2,  # Logs once per epoch.
            batch_size=batch_size)

    # Print results.
    history = history.history
    print('Validation accuracy: {acc}, loss: {loss}'.format(acc=history['val_acc'][-1], loss=history['val_loss'][-1]))

    # Save model.
    model.save('serial/'+filename+'.h5')
    return history['val_acc'][-1], history['val_loss'][-1]

def separateMissRaw(model, data, labels, v, s, save=False):
    """Returns a list of string containing misclassified samples and another containing well classified samples"""
    wrong, right = [], []
    predictions = model.predict(s.transform(v.transform(data)).astype('float32'))
    for i in range(len(data)):
        if round(predictions[i][0])==labels[i]:
            right.append(data[i])
        else:
            wrong.append(data[i])
    if save:
        path = "stats/rt/"
        with open(path+"right_samples_raw","w") as f:
            f.write("".join(right))
        with open(path+"wrong_samples_raw","w") as f:
            f.write("".join(wrong))

    return wrong, right

def separateMiss(model, data, labels):
    """Returns a list containing misclassified samples and another containing well classified samples"""
    neg, pos = [], []
    for sample, truth in list(zip(data, labels)):
        if(round(model.predict(sample)[0][0])==truth):
            pos.append(sample)
        else:
            neg.append(sample)
    return neg, pos

def getErrAnalysisStats(model, data, labels, vectorizer, save=False):
    vocab = vectorizer.get_feature_names()
    neg, pos = separateMiss(model, data, labels)
    neg_count, pos_count, stats = defaultdict(int), defaultdict(int), defaultdict(int)

    for sample in neg:
        for token_id in sample.indices:
            neg_count[vocab[token_id]]+=1
    for sample in pos:
        for token_id in sample.indices:
            pos_count[vocab[token_id]]+=1

    for key, neg_c in neg_count.items():
        stats[key] = [neg_c, pos_count[key], round(neg_c/(neg_c+pos_count[key]),3), neg_c+pos_count[key]]
    for key, pos_c in pos_count.items():
        if key not in neg_count:
            stats[key] = [0, pos_c, 0, pos_c]
    if save: 
        neg_str = [[vocab[token_id] for token_id in sample.indices] for sample in neg]
        pos_str = [[vocab[token_id] for token_id in sample.indices] for sample in pos]
        saveStats(stats, neg_str, pos_str)
    return stats, neg, pos

def saveStats(stats, neg=None, pos=None, sep=";"):
    path = "stats/rt/"
    with open(path+"wordErrorCount.csv","w") as f:
        f.write("word;wrong_count;right_count;wrong/tot;total\n")
        for key, value in stats.items():
            f.write(key+sep+sep.join([str(v) for v in value])+"\n")
    if neg is not None:
        with open(path+"wrong_samples","w") as f:
            f.write("\n".join([",".join(s) for s in neg]))
    if pos is not None:
        with open(path+"right_samples","w") as f:
            f.write("\n".join([",".join(s) for s in pos]))


# import operator
# x = {1: 2, 3: 4, 4: 3, 2: 1, 0: 0}
# sorted_x = sorted(x.items(), key=operator.itemgetter(1))       

train_texts, test_texts, train_labels, test_labels = load_rt_polarity_dataset()
num_classes = checkLabels(train_labels, test_labels)
x_train, x_test, v, s = ngram_vectorize(train_texts, train_labels, test_texts, top_k=20000, ngram_range=(1,3))

model = mlp_model(units=[8], input_shape=x_train.shape[1:], num_classes=num_classes, dropout_rate=0.2, optimizer=tf.keras.optimizers.Adam(lr=1e-3))
#train_model(model, x_train, train_labels)

# model.predict(s.transform(v.transform(["Kirito still looks 12 years old even though he's 22 or something. Tea parties still happen quite often"])).astype('float32'))
# array([[0.93839157]], dtype=float32)

# Pacing is as bad as always, too slow as seen on the first 6 episodes, or too fast like in episodes 7 and 9;Kirito still looks 12 years old even though he's 22 or something;Tea parties still happen quite often;What the heck is Kirito doing on these 2 years at the academy, he sure isn't training
# Pacing is as bad as always, too slow as seen on the first 6 episodes, or too fast like in episodes 7 and 9;What the heck is Kirito doing on these 2 years at the academy, he sure isn't training



