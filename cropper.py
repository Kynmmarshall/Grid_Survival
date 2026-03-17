import pygame
import os

def crop_to_sprite(image):
    """Crop image to bounding box of non-transparent pixels."""
    rect = image.get_bounding_rect()  # bounding box of non-transparent area
    cropped = pygame.Surface(rect.size, pygame.SRCALPHA)  # keep transparency
    cropped.blit(image, (0, 0), rect)
    return cropped

# Init pygame
pygame.init()
pygame.display.set_mode((1, 1), pygame.HIDDEN)

# Set the source and output directories
source_dir = r"C:\Users\rayan\Desktop\game development\asserts\PNG Sequences\Front - Attacking"
output_dir = r"C:\Users\rayan\Desktop\game development\asserts\PNG Sequences\Front - Attacking"

# Create output directory if it doesn't exist
os.makedirs(output_dir, exist_ok=True)

# Process images from 001 to 012 (adjust the range as needed)
for i in range(0, 13):  # 0 to 12
    # Format filename with 3-digit padding (001, 002, etc.)
    filename = os.path.join(source_dir, f"Front - Attacking_{i:03d}.png")
    output_filename = os.path.join(output_dir, f"Front - Attacking_{i:03d}.png")
    
    try:
        sprite = pygame.image.load(filename).convert_alpha()
        
        # Crop it
        cropped_sprite = crop_to_sprite(sprite)
        
        # Save to new file
        pygame.image.save(cropped_sprite, output_filename)
        
        print(f"✅ Processed: Front - Attacking_{i:03d}.png")
        
    except pygame.error as e:
        print(f"❌ Error loading {filename}: {e}")
    except Exception as e:
        print(f"❌ Unexpected error: {e}")

print(f"🎉 All done! Cropped images saved to: {output_dir}")