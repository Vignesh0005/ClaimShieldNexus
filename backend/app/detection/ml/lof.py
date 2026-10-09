from app.detection.ml.isolation_forest import OutlierModel

# Local Outlier Factor is trained with novelty=True so it can score unseen claims; scoring and
# normalisation are identical to the isolation forest wrapper.
LOFModel = OutlierModel
