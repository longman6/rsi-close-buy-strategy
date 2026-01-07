#!/bin/bash

# Configuration File Path
CONFIG_FILE="/etc/NetworkManager/conf.d/default-wifi-powersave-on.conf"

echo "=== WiFi Power Save Fix Tool ==="

# Check if the file exists
if [ ! -f "$CONFIG_FILE" ]; then
    echo "❌ Config file not found: $CONFIG_FILE"
    echo "Creating a new file..."
    sudo bash -c "echo '[connection]' > $CONFIG_FILE"
    sudo bash -c "echo 'wifi.powersave = 2' >> $CONFIG_FILE"
else
    echo "✅ Found config file: $CONFIG_FILE"
    
    # Check current setting
    CURRENT_SETTING=$(grep "wifi.powersave" "$CONFIG_FILE")
    echo "   Current Setting: $CURRENT_SETTING"
    
    if [[ "$CURRENT_SETTING" == *"wifi.powersave = 2"* ]]; then
        echo "🎉 WiFi Power Save is already DISABLED (2). No changes needed."
        exit 0
    fi

    # Backup
    echo "📦 Backing up original file..."
    sudo cp "$CONFIG_FILE" "${CONFIG_FILE}.bak"

    # Modify (3 -> 2)
    # 3 = Enable, 2 = Disable
    echo "🔧 Disabling WiFi Power Save..."
    sudo sed -i 's/wifi.powersave = 3/wifi.powersave = 2/g' "$CONFIG_FILE"
fi

# Verification
NEW_SETTING=$(grep "wifi.powersave" "$CONFIG_FILE")
echo "   New Setting: $NEW_SETTING"

if [[ "$NEW_SETTING" == *"wifi.powersave = 2"* ]]; then
    echo "✅ Configuration updated successfully."
else
    echo "❌ Failed to update configuration. Please check manually."
    exit 1
fi

# Restart Network Manager
echo "🔄 Restarting NetworkManager Service..."
sudo systemctl restart NetworkManager

echo "✅ Done! Please test suspend/resume now."
