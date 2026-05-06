import pygame

i=0

def resize(image):
    """Crop image to bounding box of non-transparent pixels."""
    resized=pygame.transform.scale(image,(700,700))
    
    #resized.blit(image, (0, 0), rect)
    return resized
nameAnime = "Back - Running"
character = "Female Goblin"
anime = "running"
# Init pygame (needed for image functions)
pygame.init()
pygame.display.set_mode((1, 1), pygame.HIDDEN)
while(i<12):
    if i < 10:
        sprite = pygame.image.load(f"Assets\Characters\{character}\{anime}\{nameAnime}\{nameAnime}_00{i}.png").convert_alpha()
    elif i>=10:
        sprite = pygame.image.load(f"Assets\Characters\{character}\{anime}\{nameAnime}\{nameAnime}_0{i}.png").convert_alpha()

    # Crop it
    resized_sprite = resize(sprite)

    # Save to new file
    if i < 10:
        pygame.image.save(resized_sprite, f"Assets\Characters\{character}\{anime}\{nameAnime}\{nameAnime}_00{i}.png")
    else:
        pygame.image.save(resized_sprite, f"Assets\Characters\{character}\{anime}\{nameAnime}\{nameAnime}_0{i}.png")
    i+=1

print("✅ Saved resized sprite as sprite_resized.png")