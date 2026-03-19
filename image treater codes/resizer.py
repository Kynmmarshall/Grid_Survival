import pygame

i=1

def resize(image):
    """Crop image to bounding box of non-transparent pixels."""
    resized=pygame.transform.scale(image,(500,170))
    #resized.blit(image, (0, 0), rect)
    return resized

# Init pygame (needed for image functions)
pygame.init()
pygame.display.set_mode((1, 1), pygame.HIDDEN)
while(i<16):
    #if i < 10:
    sprite = pygame.image.load(f"Assets\Questions\High\{i}.png")
    #elif i>=10:
     #   sprite = pygame.image.load(f"cropper\\toberesized\enemy3\Walking\Wraith_02_Moving Forward_0{i}.png").convert_alpha()

    # Crop it
    resized_sprite = resize(sprite)

    # Save to new file
    pygame.image.save(resized_sprite, f"{i}.png")
    i+=1

print("✅ Saved resized sprite as sprite_resized.png")