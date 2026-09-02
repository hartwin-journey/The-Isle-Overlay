# AI category icons

PNG markers drawn for entries in [`data/ai.json`](../../../data/ai.json), one per `category`. The map renderers ([`ui/map_canvas.py`](../../map_canvas.py)) looks up a file here by slugifying the category: lower-cased, spaces replaced with underscores, `.png` appended.

Square PNGs with transparency work best; They are scaled to 24px on the Full Map and 18px on the Mini Map, keeping a constant on-screen size at any zoom.

If a category has no matching PNG here, that marker automatically falls back to the original colored dot, so icons can be added one at a time.

Icons are taken from the `Flat Circular Flat` pack from [https://www.flaticon.com/free-icon/](https://www.flaticon.com/free-icon/). Source Attribution is mentioned below.

| `category` in ai.json | file name            | Source                                                                                                                                      |
|-----------------------|----------------------|---------------------------------------------------------------------------------------------------------------------------------------------|
| Boar                  | `boar.png`           | <a href="https://www.flaticon.com/free-icons/animal" title="animal icons">Animal icons created by Magnific - Flaticon</a>                   |
| Chicken               | `chicken.png`        | <a href="https://www.flaticon.com/free-icons/hen" title="hen icons">Hen icons created by Magnific - Flaticon</a>                            |
| Crab                  | `crab.png`           | <a href="https://www.flaticon.com/free-icons/crab" title="crab icons">Crab icons created by Magnific - Flaticon</a>                         |
| Deer                  | `deer.png`           | <a href="https://www.flaticon.com/free-icons/animals" title="animals icons">Animals icons created by Magnific - Flaticon</a>                |
| Deinosuchus AI        | `deinosuchus_ai.png` | <a href="https://www.flaticon.com/free-icons/alligator" title="Alligator icons">Alligator icons created by Magnific - Flaticon</a>          |
| Fish                  | `fish.png`           | <a href="https://www.flaticon.com/free-icons/fish" title="fish icons">Fish icons created by Magnific - Flaticon</a>                         |
| Frog                  | `frog.png`           | <a href="https://www.flaticon.com/free-icons/frog" title="frog icons">Frog icons created by Magnific - Flaticon</a>                         |
| Gallimimus AI         | `gallimimus_ai.png`  | <a href="https://www.flaticon.com/free-icons/dinosaur" title="dinosaur icons">Dinosaur icons created by Magnific - Flaticon</a>             |
| Gastrolith            | `gastrolith.png`     | <a href="https://www.flaticon.com/free-icons/rocks" title="rocks icons">Rocks icons created by Magnific - Flaticon</a>                      |
| Goat                  | `goat.png`           | <a href="https://www.flaticon.com/free-icons/goat" title="goat icons">Goat icons created by Magnific - Flaticon</a>                         |
| Rabbit                | `rabbit.png`         | <a href="https://www.flaticon.com/free-icons/rabbit" title="rabbit icons">Rabbit icons created by Magnific - Flaticon</a>                   |
| Taco                  | `taco.png`           | <a href="https://www.flaticon.com/free-icons/paleontology" title="Paleontology icons">Paleontology icons created by Magnific - Flaticon</a> |
| Turtle                | `turtle.png`         | <a href="https://www.flaticon.com/free-icons/turtle" title="turtle icons">Turtle icons created by Magnific - Flaticon</a>                   |
