#Add player2 dance frames
player2_dance_frames = [
    pygame.image.load("assets/player2_dance1.png"),
    pygame.image.load("assets/player2_dance2.png"),
    pygame.image.load("assets/player2_dance3.png")
]

#create dance animations
def player2_dance(screen, clock, player2_pos):
    frame = 0
    speed = 0.2
    running = True

    while running:
        screen.fill((30, 30, 30))  # or your game background

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                exit()

        # Animate
        frame += speed
        if frame >= len(player2_dance_frames):
            frame = 0

        # Draw Player2 dancing
        screen.blit(player2_dance_frames[int(frame)], player2_pos)

        pygame.display.update()
        clock.tick(60)

        # Stop after some time (e.g. 5 seconds)
        pygame.time.delay(50)

#Trigger for the dance to begin after level 1
if level == 1 and level_complete:
player2_dance(screen, clock, player2_pos)
