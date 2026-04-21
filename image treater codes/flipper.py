import pygame
import os

pygame.init()

# Create the output directory if it doesn't exist
output_dir = r"Assets\Characters\Ninja\Running\Right - Running"
os.makedirs(output_dir, exist_ok=True)

i = 0
while i < 4:  # Adjust the range as needed
    if i < 10:
        # Input file
        path = rf"Assets\Characters\Ninja\Running\Right - Running\Right - Running_00{i}.png"
        
        # Output file - fixed naming to use "Left" instead of "Right"
        output_path = rf"Assets\Characters\Ninja\idle\Left - Idle Blinking\Left - Idle Blinking_00{i}.png"
    else:
        # Input file
        path = rf"Assets\Characters\Ninja\idle\Right - Idle Blinking\Right - Idle Blinking_0{i}.png"
        
        # Output file - fixed naming to use "Left" instead of "Right"
        output_path = rf"Assets\Characters\Ninja\idle\Left - Idle Blinking\Left - Idle Blinking_0{i}.png"
    
    try:
        # Load the image
        image = pygame.image.load(path)
        
        # Flip horizontally
        flipped = pygame.transform.flip(image, True, False)
        
        # Save the flipped image
        pygame.image.save(flipped, output_path)
        print(f"Flipped and saved: {output_path}")
    except FileNotFoundError:
        print(f"File not found: {path}")
    except Exception as e:
        print(f"Error processing {path}: {e}")
    
    i += 1

pygame.quit()
print("All images processed!")