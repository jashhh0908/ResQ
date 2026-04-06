import torch
import torch.nn as nn

class ConvBlock(nn.Module):
    def __init__(self, in_channels, out_channels):
        super().__init__()
        self.conv1 = nn.Conv2d(in_channels, out_channels, kernel_size=3, padding=1)
        self.bn1 = nn.BatchNorm2d(out_channels)
        self.relu1 = nn.ReLU(inplace=True)
        self.conv2 = nn.Conv2d(out_channels, out_channels, kernel_size=3, padding=1)
        self.bn2 = nn.BatchNorm2d(out_channels)
        self.relu2 = nn.ReLU(inplace=True)

    def forward(self, x):
        x = self.conv1(x)
        x = self.bn1(x)
        x = self.relu1(x)
        x = self.conv2(x)
        x = self.bn2(x)
        x = self.relu2(x)
        return x

class UNet(nn.Module):
    def __init__(self):
        super().__init__()
        self.pool = nn.MaxPool2d(kernel_size=2, stride=2)
        
        # Encoder (downsampling)
        self.enc1 = ConvBlock(1, 64)
        self.enc2 = ConvBlock(64, 128)
        self.enc3 = ConvBlock(128, 256)
        
        # Bottleneck
        self.bottleneck = ConvBlock(256, 512)
        
        # Decoder (upsampling)
        # Note: upconv outputs matching dimension, then we concat skip connection
        self.upconv3 = nn.ConvTranspose2d(512, 256, kernel_size=2, stride=2)
        # 256 (upsampled) + 256 (skip) = 512 channels into dec3
        self.dec3 = ConvBlock(512, 256)
        
        self.upconv2 = nn.ConvTranspose2d(256, 128, kernel_size=2, stride=2)
        # 128 (upsampled) + 128 (skip) = 256 channels into dec2
        self.dec2 = ConvBlock(256, 128)
        
        self.upconv1 = nn.ConvTranspose2d(128, 64, kernel_size=2, stride=2)
        # 64 (upsampled) + 64 (skip) = 128 channels into dec1
        self.dec1 = ConvBlock(128, 64)
        
        # Output
        self.out_conv = nn.Conv2d(64, 1, kernel_size=1)
        self.sigmoid = nn.Sigmoid()

    def forward(self, x):
        # Encoder
        e1 = self.enc1(x)
        e2 = self.enc2(self.pool(e1))
        e3 = self.enc3(self.pool(e2))
        
        # Bottleneck
        b = self.bottleneck(self.pool(e3))
        
        # Decoder
        d3 = self.upconv3(b)
        d3 = torch.cat((e3, d3), dim=1) # skip connection 3
        d3 = self.dec3(d3)
        
        d2 = self.upconv2(d3)
        d2 = torch.cat((e2, d2), dim=1) # skip connection 2
        d2 = self.dec2(d2)
        
        d1 = self.upconv1(d2)
        d1 = torch.cat((e1, d1), dim=1) # skip connection 1
        d1 = self.dec1(d1)
        
        # Output
        out = self.out_conv(d1)
        return self.sigmoid(out)

if __name__ == "__main__":
    # Quick sanity check
    model = UNet()
    dummy_input = torch.randn(1, 1, 256, 256)
    out = model(dummy_input)
    print(f"Output shape: {out.shape}")  # Expected: [B, 1, 256, 256]
