import pygame

i=0

def crop_to_sprite(image):
    """Crop image to bounding box of non-transparent pixels."""
    rect = image.get_bounding_rect()  # bounding box of non-transparent area
    cropped = pygame.Surface(rect.size, pygame.SRCALPHA)  # keep transparency
    cropped.blit(image, (0, 0), rect)
    return cropped

# Init pygame (needed for image functions)
pygame.init()
pygame.display.set_mode((1, 1), pygame.HIDDEN)
while(i<12):
    if i < 10:
        sprite = pygame.image.load(f"cropper\\tobecropped\enemy3\Walking\Wraith_02_Moving Forward_00{i}.png").convert_alpha()
    elif i>=10:
        sprite = pygame.image.load(f"cropper\\tobecropped\enemy3\Walking\Wraith_02_Moving Forward_0{i}.png").convert_alpha()

    # Crop it
    cropped_sprite = crop_to_sprite(sprite)

    # Save to new file
    pygame.image.save(cropped_sprite, f"{i}.png")
    i+=1

print("✅ Saved cropped sprite as sprite_cropped.png")