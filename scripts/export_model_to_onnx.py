"""
Export Keras hybrid DL feature extractor to ONNX format.

This script takes the .keras hybrid model, isolates the penultimate Dense layer
('feature_dense', 10 neurons), and exports it into a lightweight ONNX model
to be used with ONNX Runtime in the bot.

Usage:
    python scripts/export_model_to_onnx.py
"""
import os
import sys
import tensorflow as tf
from tensorflow.keras.models import load_model, Model
import tf2onnx


def export_feature_extractor(
    keras_path: str = "models/hybridre_cnn_gru_dense_xgboost_return_1.4185.keras",
    onnx_path: str = "models/feature_extractor.onnx"
):
    """Load Keras model, isolate feature_dense sub-model, and export to ONNX."""
    if not os.path.exists(keras_path):
        raise FileNotFoundError(f"Keras model not found at {keras_path}")

    print(f"Loading Keras model from {keras_path}...")
    full_model = load_model(keras_path)
    full_model.summary()

    # The penultimate layer is named 'feature_dense' (10 units)
    try:
        feature_layer = full_model.get_layer("feature_dense")
        feature_extractor = Model(inputs=full_model.inputs, outputs=feature_layer.output)
    except Exception:
        # Fallback to layer at index -2
        feature_extractor = Model(inputs=full_model.inputs, outputs=full_model.layers[-2].output)

    print("\nFeature extractor sub-model summary:")
    feature_extractor.summary()

    os.makedirs(os.path.dirname(onnx_path), exist_ok=True)

    print(f"\nConverting feature extractor to ONNX: {onnx_path} ...")
    input_signature = [
        tf.TensorSpec([None, 60, 11], tf.float32, name="candles_sequence")
    ]

    model_proto, _ = tf2onnx.convert.from_keras(
        feature_extractor,
        input_signature=input_signature,
        opset=17,
        output_path=onnx_path
    )

    print(f"ONNX model successfully saved to: {onnx_path}")
    print(f"ONNX Model size: {os.path.getsize(onnx_path):,} bytes")


if __name__ == "__main__":
    export_feature_extractor()
