import math
from torchvision.models.detection.faster_rcnn import FastRCNNPredictor
from torchvision.models.detection.ssd import SSDClassificationHead
import torchvision
import os
import torch
from custom_roi_heads import CustomRoIHeads, FastRCNNPredictorWithAuthor
from torchvision.models.detection.rpn import RPNHead, AnchorGenerator

def set_anchor(model, args):
  """
  This function allows you to customize the anchor generator with user-defined sizes and aspect ratios.
  """
  tuple_sizes_list = []
  tuple_aspect_ratios_list = []
  if args.size8:
    tuple_sizes_list.append((8,))
  if args.size16:
    tuple_sizes_list.append((16,))
  if args.size32:
    tuple_sizes_list.append((32,))
  if args.size64:
    tuple_sizes_list.append((64,))
  if args.size128:
    tuple_sizes_list.append((128,))
  if args.size256:
    tuple_sizes_list.append((256,))
  if args.size512:
    tuple_sizes_list.append((512,))
  if args.ar05:
     tuple_aspect_ratios_list.append(0.5)
  if args.ar1:
     tuple_aspect_ratios_list.append(1.0)
  if args.ar2:
     tuple_aspect_ratios_list.append(2.0)
  if len(tuple_sizes_list) !=5:
    # check the number of sizes (number of outputs of FPN is equal to 5)
    print("Number of sizes must be equal to 5")
    os._exit(1)
  # create tuple for anchors sizes
  sizes = tuple(tuple_sizes_list)
  # create tuple for anchors aspect ratios
  aspect_ratios = ((tuple(tuple_aspect_ratios_list)),) * len(sizes)
  # replace default sizes with custom sizes
  model.rpn.anchor_generator.sizes = sizes
  # replace default aspect ratios with custom aspect ratios
  model.rpn.anchor_generator.aspect_ratios = aspect_ratios
  anchor_generator = AnchorGenerator(
  sizes=sizes,
  aspect_ratios=tuple([tuple(tuple_aspect_ratios_list) for _ in range(5)]))
  # replace anchor_generator with custom generator
  model.rpn.anchor_generator = anchor_generator
  # 256 because that's the number of features that FPN returns
  model.rpn.head = RPNHead(256, anchor_generator.num_anchors_per_location()[0])

def create_model(n_classes, n_authors, args):

  """
  Create custom model for object detection.
  Supported models from torchvision: Faster R-CNN, RetinaNet, SSD300.
  Available backbone for Faster R-CNN: ResNet50, MobileNetV3-Large.
  """

  if args.model == "fasterrcnn":

    if args.backbone == "resnet50":
      # create Faster R-CNN model with ResNet50-FPN backbone
      model = torchvision.models.detection.fasterrcnn_resnet50_fpn(weights=('DEFAULT' if args.pretrained else None), trainable_backbone_layers=args.trainable_backbone_layers)

    elif args.backbone == "resnet50v2":
      # create Faster R-CNN model with ResNet50-FPN backbone
      model = torchvision.models.detection.fasterrcnn_resnet50_fpn_v2(weights=('DEFAULT' if args.pretrained else None), trainable_backbone_layers=args.trainable_backbone_layers)

    elif args.backbone == "mobilenet":
      # create Faster R-CNN model with MobileNetV3-Large backbone
      model = torchvision.models.detection.fasterrcnn_mobilenet_v3_large_fpn(weights=('DEFAULT' if args.pretrained else None), trainable_backbone_layers=args.trainable_backbone_layers)

    model = create_fasterrcnn(n_classes, n_authors, model, args)

  elif args.model == "retinanet":
    # create RetinaNet model with ResNet50-FPN backbone
    model = create_retinanet(n_classes, args)
  
  elif args.model == "ssd":
    # create SSD300 model with VGG-16 backbone
    model = create_ssd300(n_classes, args)
    
  return model

def create_fasterrcnn(n_classes, n_authors, model, args):

  """
  Create FasterRCNN for custom classes.
  The following model builder can be used to istantiate a FasterRCNN model with or without pretrained weights.
  All the supported models internally rely on torchvision.models.detection.faster_rcnn.FasterRCNN base class.
  Author classification is also supported if the user requests it via command line. 
  In this case, some of the main function of RoIHeads are modified to support the new branch.
  """
  
  # get the number of input features
  in_features = model.roi_heads.box_predictor.cls_score.in_features

  if args.add_authors:
    # change the default RoIHeads with CustomRoIHeads
    model.roi_heads = CustomRoIHeads(model.roi_heads.box_roi_pool, model.roi_heads.box_head, model.roi_heads.box_predictor, args.box_fg_iou_threshold, args.box_bg_iou_threshold, model.roi_heads.fg_bg_sampler.batch_size_per_image, model.roi_heads.fg_bg_sampler.positive_fraction, model.roi_heads.box_coder.weights, args.box_score_threshold, args.box_nms_threshold, args.box_detections_per_img)
    # change the default FastRCNNPredictor (the top level head) with a custom FastRCNNPredictor
    model.roi_heads.box_predictor = FastRCNNPredictorWithAuthor(in_features, n_classes, n_authors)
  
  else:
    # define a new head for the detector with required number of classes
    model.roi_heads.box_predictor = FastRCNNPredictor(in_features, n_classes)

    # setting classification network threshold values
    model.roi_heads.nms_thresh = args.box_nms_threshold
    model.roi_heads.score_thresh = args.box_score_threshold
    model.roi_heads.proposal_matcher.low_threshold = args.box_bg_iou_threshold
    model.roi_heads.proposal_matcher.high_threshold = args.box_fg_iou_threshold
    model.roi_heads.detections_per_img = args.box_detections_per_img


  # setting RPN network threshold values

  model.rpn.nms_thresh = args.rpn_nms_threshold
  model.rpn.proposal_matcher.low_threshold = args.rpn_fg_iou_threshold
  model.rpn.proposal_matcher.high_threshold = args.rpn_bg_iou_threshold
  model.rpn.score_thresh = args.rpn_score_threshold

  if args.custom_anchors:
    # set sizes and aspect ratio of anchors
    set_anchor(model, args)
  print("Anchors sizes: " + str(model.rpn.anchor_generator.sizes))
  print("Anchors aspect ratios: " + str(model.rpn.anchor_generator.aspect_ratios))

  return model

def create_retinanet(n_classes, args):

  """
  Create RetinaNet for custom classes.
  The following model builder can be used to istantiate a RetinaNet model with or without pretrained weights.
  All the supported models internally rely on torchvision.models.detection.retinanet.RetinaNet base class.
  """

  # load model
  model = torchvision.models.detection.retinanet_resnet50_fpn_v2(weights=('DEFAULT' if args.pretrained else None))
  num_anchors = model.head.classification_head.num_anchors
  model.head.classification_head.num_classes = n_classes

  cls_logits = torch.nn.Conv2d(256, num_anchors * n_classes, kernel_size = 3, stride=1, padding=1)
  torch.nn.init.normal_(cls_logits.weight, std=0.01)
  torch.nn.init.constant_(cls_logits.bias, -math.log((1 - 0.01) / 0.01))
  # assign cls head to model
  model.head.classification_head.cls_logits = cls_logits

  return model

def create_ssd300(n_classes, args):
  """
  Create SSD300 for custom classes.
  The following model builder can be used to istantiate a SSD300 model with or without pretrained weights.
  All the supported models internally rely on torchvision.models.detection.ssd300.SSD base class.
  """
  model = torchvision.models.detection.ssd300_vgg16(weights=('DEFAULT' if args.pretrained else None))
  num_anchors = model.anchor_generator.num_anchors_per_location() # get num anchor
  in_channels=[]
  for layer in model.head.classification_head.module_list:
    in_channels.append(layer.in_channels)
  # add new classification head with custom number of classes
  model.head.classification_head = SSDClassificationHead(in_channels, num_anchors, n_classes)
  return model
