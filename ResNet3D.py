# -*- coding: utf-8 -*-
"""ResNet3D.ipynb

Automatically generated by Colab.

Original file is located at
    https://colab.research.google.com/drive/1cNWgBRKPDyCyiAPOIHYlKXG_YK2XANBc
"""

# Commented out IPython magic to ensure Python compatibility.
import cv2
import os
import numpy as np
import random
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score
import torch
import torchvision.transforms as transforms
import torchvision.datasets as datasets
import torch.nn as nn
import torch.nn.functional as F
from torchvision.models.video import r3d_18
from torch.utils.data import Dataset, DataLoader
import mediapipe as mp
import matplotlib.pyplot as plt
from imutils import face_utils
from PIL import Image, ImageEnhance

# %matplotlib inline

facial_expression = {
    'Angry' :     0,
    'Happy' :     1,
    'Neutral' :   2,
    'Sad' :       3,
    'Surprise' :  4,
    'Fear' :      5,
    'Disgust' :   6
}

def split_dataset(train_dir, test_dir, val_ratio=0.2, seed=42):
    random.seed(seed)

    def extract_video_paths_and_labels(data_dir):

        video_paths, video_labels = [], []

        for label_name in os.listdir(data_dir):
            label_dir = os.path.join(data_dir, label_name)
            if not os.path.isdir(label_dir):
                continue

            video_to_frames = {}
            for frame_name in sorted(os.listdir(label_dir)):
                frame_name = frame_name.strip()
                video_id = '_'.join(frame_name.split('_')[:-1])
                frame_path = os.path.join(label_dir, frame_name)

                if video_id not in video_to_frames:
                    video_to_frames[video_id] = []
                video_to_frames[video_id].append(frame_path)

            for frames in video_to_frames.values():
                video_paths.append(frames)
                video_labels.append(facial_expression.get(label_name, -1))

        return video_paths, video_labels


    train_video_paths, train_video_labels = extract_video_paths_and_labels(train_dir)
    test_paths, test_labels = extract_video_paths_and_labels(test_dir)


    train_paths, val_paths, train_labels, val_labels = train_test_split(
        train_video_paths, train_video_labels, test_size=val_ratio, random_state=seed
    )

    return train_paths, val_paths, test_paths, train_labels, val_labels, test_labels

def video_to_frames(video_path, output_dir, fps=5):
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise ValueError(f"Cannot open the video file: {video_path}")

    video_fps = cap.get(cv2.CAP_PROP_FPS)
    frame_interval = int(video_fps / fps)

    frame_count = 0
    saved_count = 0

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        if frame_count % frame_interval == 0:
            frame_name = os.path.join(output_dir, f"frame_{saved_count:06d}.png")
            cv2.imwrite(frame_name, frame)
            saved_count += 1

        frame_count += 1

    cap.release()
    print(f"Saved {saved_count} frames to: {output_dir}")

mp_face_detection = mp.solutions.face_detection
mp_face_mesh = mp.solutions.face_mesh
face_detection = mp_face_detection.FaceDetection(min_detection_confidence=0.5)
face_mesh = mp_face_mesh.FaceMesh(static_image_mode=True, max_num_faces=1)

def detect_face_and_landmarks(frame):
    rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    # Use Pillow to enhance the image
    pillow_image = Image.fromarray(rgb_frame)
    # Enhance sharpness
    # sharpness_enhancer = ImageEnhance.Sharpness(pillow_image)
    # sharpened_image = sharpness_enhancer.enhance(4.0)
    # Enhance contrast
    contrast_enhancer = ImageEnhance.Contrast(pillow_image)
    enhanced_image = contrast_enhancer.enhance(2.0)
    enhanced_image = np.array(enhanced_image)

    # Detect faces using MediaPipe Face Detection
    face_detection_results = face_detection.process(enhanced_image)
    if face_detection_results.detections:
        for detection in face_detection_results.detections:
            bboxC = detection.location_data.relative_bounding_box
            h, w, _ = frame.shape
            x_min = int(bboxC.xmin * w)
            y_min = int(bboxC.ymin * h)
            x_max = int((bboxC.xmin + bboxC.width) * w)
            y_max = int((bboxC.ymin + bboxC.height) * h)

            # Expand the bounding box by 20%
            x_min = max(0, x_min - int(0.1 * (x_max - x_min)))
            y_min = max(0, y_min - int(0.1 * (y_max - y_min)))
            x_max = min(w, x_max + int(0.1 * (x_max - x_min)))
            y_max = min(h, y_max + int(0.1 * (y_max - y_min)))

            # Crop and zoom in on the face
            face_roi = frame[y_min:y_max, x_min:x_max]
            frame = cv2.resize(face_roi, (frame.shape[1], frame.shape[0]))

            # Use Pillow to enhance the image
            pillow_image = Image.fromarray(frame)
            # Enhance sharpness
            sharpness_enhancer = ImageEnhance.Sharpness(pillow_image)
            enhanced_image = sharpness_enhancer.enhance(4.0)
            # Enhance contrast
            # contrast_enhancer = ImageEnhance.Contrast(sharpened_image)
            # enhanced_image = contrast_enhancer.enhance(2.0)
            enhanced_image = np.array(enhanced_image)

    # tect facial landmarks
    results = face_mesh.process(cv2.cvtColor(enhanced_image, cv2.COLOR_BGR2RGB))
    if results.multi_face_landmarks:
        for face_landmarks in results.multi_face_landmarks:
            for landmark in face_landmarks.landmark:
                x = int(landmark.x * frame.shape[1])
                y = int(landmark.y * frame.shape[0])
                cv2.circle(frame, (x, y), 1, (0, 255, 0), -1)  # Draw facial landmarks
    return frame

def process_image(input_path, max_frames=10, resize=(112, 112)):

    frames = []

    def read_and_process_frame(frame):
        frame = detect_face_and_landmarks(frame)
        frame = cv2.resize(frame, resize)
        return frame.astype(np.float32) / 255.0

    if isinstance(input_path, list):
        for path in input_path:
            if isinstance(path, str) and os.path.isfile(path):
                # print(f"Reading file: {path}")
                if path.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp')):
                    frame = cv2.imread(path)
                    if frame is not None:
                        processed_frame = read_and_process_frame(frame)
                        frames.append(processed_frame)
                    else:
                        print(f"Warning: Failed to read {path}")
                else:
                    print(f"Warning: Unsupported file format for {path}")
            else:
                print(f"Warning: Invalid file path {path}")

    elif isinstance(input_path, str) and os.path.isfile(input_path):
        # print(f"Reading file: {input_path}")
        if input_path.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp')):
            frame = cv2.imread(input_path)
            if frame is not None:
                processed_frame = read_and_process_frame(frame)
            frames.append(processed_frame)
        else:
            print(f"Warning: Unsupported video format for {input_path}")

    if len(frames) > 0 and len(frames) < max_frames:
        frames.extend([frames[-1]] * (max_frames - len(frames)))
    elif len(frames) > max_frames:
        frames = frames[:max_frames]

    # print(f"Shape after process_image: {np.array(frames).shape}")
    return np.array(frames)  # shape: (seq_len, height, width, channels)

def augment_frames(frames):
    """
    Args:
        frames: shape (seq_len, height, width, channels)
    Returns:
        augmented frames
    """
    transform = transforms.Compose([
        transforms.ToPILImage(),
        transforms.RandomRotation(2),
        transforms.ColorJitter(brightness=0.2, contrast=0.2, saturation=0.2, hue=0.1),
        transforms.ToTensor(),
        transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])
    ])
    augmented_frames = []

    for frame in frames:
        frame = (frame * 255).astype(np.uint8) if frame.max() <= 1 else frame
        augmented_frame = transform(frame)
        augmented_frames.append(augmented_frame)

    # print(f"Shape after augment_frames: {np.array(augmented_frames).shape}")
    return torch.stack(augmented_frames)  # shape: (seq_len, height, width, channels)

class ResNet3DModel(nn.Module):
    def __init__(self, num_classes):
        super(ResNet3DModel, self).__init__()
        self.backbone = r3d_18(pretrained=True)

        self.backbone.fc = nn.Linear(self.backbone.fc.in_features, num_classes)

    def forward(self, x):
        return self.backbone(x)

class VideoImageDataset(Dataset):
    def __init__(self, video_paths, labels=None, transform=None, clip_length=10, resize=(112, 112)):
        self.video_paths = video_paths
        self.labels = labels
        self.transform = transform
        self.clip_length = clip_length
        self.resize = resize

    def __len__(self):
        return len(self.video_paths)

    def __getitem__(self, idx):
        frame_paths = self.video_paths[idx]  # get all videos' paths
        label = self.labels[idx]  # get the coresponding labels

        frames = self._load_and_process_frames(frame_paths)

        if self.transform:
            frames = self.transform(frames)
            frames = np.transpose(frames, (1, 0, 2, 3))
        else:
            frames = np.transpose(frames, (3, 1, 2, 0))

        frames = torch.tensor(frames, dtype=torch.float32)
        # frames = frames.unsqueeze(0)

        label = torch.tensor(label, dtype=torch.long)

        # print(f"Shape after torch.transpose: {np.array(frames).shape}")
        return frames, label

    def _load_and_process_frames(self, frame_paths):
        """
        Returns:
            np.ndarray: shape = (clip_length, height, width, channels)
        """
        frames = process_image(frame_paths, max_frames=self.clip_length, resize=self.resize)

        # print(f"Shape after _load_and_process_frames: {np.array(frames).shape}")
        return frames

def collate_fn(batch):
    inputs, labels = zip(*batch)
    inputs = torch.stack([torch.tensor(input) for input in inputs], dim=0)
    labels = torch.tensor(labels, dtype=torch.long)
    # print("inputs' shape after collate_fn: ", inputs.shape)
    # print("labels' shape after collate_fn: ", labels.shape)
    return inputs, labels

"""Training process part:"""

# lr = 0.00001
# num_epochs = 20
# batch_size = 64
# num_classes = 7

# train_dir = "./input_videos/Training"
# test_dir = "./input_videos/Testing"

# train_paths, val_paths, test_paths, train_labels, val_labels, test_labels =  split_dataset(
#     train_dir, test_dir, 0.2
# )
# print("Len of train_paths: ", len(train_paths))
# print("Len of val_paths: ", len(val_paths))
# print("Len of test_paths: ", len(test_paths))

# train_dataset = VideoImageDataset(train_paths, train_labels, transform=augment_frames)
# val_dataset = VideoImageDataset(val_paths, val_labels, transform=augment_frames)
# test_dataset = VideoImageDataset(test_paths, test_labels, transform=augment_frames)

# train_loader = DataLoader(train_dataset, batch_size=batch_size, shuffle=True, collate_fn=collate_fn)
# val_loader = DataLoader(val_dataset, batch_size=batch_size, shuffle=False, collate_fn=collate_fn)
# test_loader = DataLoader(test_dataset, batch_size=batch_size, shuffle=False, collate_fn=collate_fn)

# device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')

# model = ResNet3DModel(num_classes=7).to(device)
# criterion = nn.CrossEntropyLoss()
# optimizer = torch.optim.Adam(model.parameters(), lr=lr, weight_decay=0.01)
# optimizer = torch.optim.Adam(model.fc.parameters(), lr=lr)

# train_losses = []
# val_losses = []

# for epoch in range(num_epochs):
#     model.train()
#     train_loss = 0
#     train_preds = []
#     train_labels = []

#     for inputs, labels in train_loader:
#         inputs, labels = inputs.to(device), labels.to(device)
#         outputs = model(inputs)
#         loss = criterion(outputs, labels)

#         optimizer.zero_grad()
#         loss.backward()
#         optimizer.step()

#         train_loss += loss.item()
#         _, preds = torch.max(outputs, 1)
#         train_preds.extend(preds.cpu().numpy())
#         train_labels.extend(labels.cpu().numpy())

#     train_acc = accuracy_score(train_labels, train_preds)
#     avg_train_loss = train_loss/len(train_loader)
#     train_losses.append(avg_train_loss)
#     # print("Gound Truth: ", train_labels)
#     # print("Predictions: ", train_preds)
#     print(f"Epoch {epoch+1}/{num_epochs}, Training Loss: {avg_train_loss:.4f},  Training Accuracy: {train_acc:.4f}")


#     model.eval()
#     val_loss = 0
#     val_preds = []
#     val_labels = []

#     with torch.no_grad():
#         for inputs, labels in val_loader:
#             inputs, labels = inputs.to(device), labels.to(device)
#             outputs = model(inputs)
#             loss = criterion(outputs, labels)
#             val_loss += loss.item()

#             _, preds = torch.max(outputs, 1)
#             val_preds.extend(preds.cpu().numpy())
#             val_labels.extend(labels.cpu().numpy())

#     val_acc = accuracy_score(val_labels, val_preds)
#     avg_val_loss = val_loss / len(val_loader)
#     val_losses.append(avg_val_loss)
#     # print("Gound Truth: ", train_labels)
#     # print("Predictions: ", train_preds)
#     print(f"Epoch {epoch+1}/{num_epochs}, Validation Loss: {avg_val_loss:.4f}, Validation Accuracy: {val_acc:.4f}")

# plt.figure(figsize=(10, 6))
# plt.plot(range(1, num_epochs + 1), train_losses, label='Training Loss', color='blue', linestyle='-')
# plt.plot(range(1, num_epochs + 1), val_losses, label='Validation Loss', color='orange', linestyle='-')
# plt.xlabel('Epoch')
# plt.ylabel('Loss')
# plt.title('Training and Validation Loss')
# plt.legend()
# plt.grid(True)
# plt.show()

"""Predict new videos part:"""

# model.eval()
# test_accuracy = 0
# with torch.no_grad():
#     for inputs, labels in test_loader:
#         inputs, labels = inputs.to(device), labels.to(device)
#         outputs = model(inputs)
#         _, preds = torch.max(outputs, 1)
#         test_accuracy += torch.sum(preds == labels).item()
# test_accuracy /= len(test_dataset)
# print(f"Test Accuracy: {test_accuracy:.4f}")

# saved_model_dir = "./saved_models_test"
# save_model_name = "test_model_v4pth"
# save_model_path = os.path.join(saved_model_dir, save_model_name)

# torch.save(model.state_dict(), save_model_path)
# print(f"Model weights saved to {save_model_path}")