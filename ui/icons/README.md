# AI category icons

PNG markers drawn for entries in [`data/ai.json`](../../data/ai.json), one per `category`. The map renderers ([`ui/map_canvas.py`](../map_canvas.py)) looks up a file here by slugifying the category: lower-cased, spaces replaced with underscores, `.png` appended.

PNGs with transparency work best; They are scaled to 24px on the Full Map and 18px on the Mini Map, keeping a constant on-screen size at any zoom.

If a category has no matching PNG here, that marker automatically falls back to the original colored dot, so icons can be added one at a time.

Icons are taken from the `Flat Circular Flat` pack from [https://www.flaticon.com/free-icon/](https://www.flaticon.com/free-icon/). Source Attribution is mentioned below.

### Icons for AI

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

### Icons for food

| `category` in food.json | file name          | Source                                                                                                                                |
|-------------------------|--------------------|---------------------------------------------------------------------------------------------------------------------------------------|
| Agave                   | `agave.png`        | <a href="https://www.flaticon.com/free-icons/plant" title="plant icons">Plant icons created by Magnific - Flaticon</a>                |
| Ash                     | `ash.png`          | <a href="https://www.flaticon.com/free-icons/ash" title="ash icons">Ash icons created by Magnific - Flaticon</a>                      |
| Azure Apol              | `azure_apol.png`   | <a href="https://www.flaticon.com/free-icons/plant" title="plant icons">Plant icons created by Magnific - Flaticon</a>                |
| Banana                  | `banana.png`       | <a href="https://www.flaticon.com/free-icons/banana" title="banana icons">Banana icons created by Magnific - Flaticon</a>             |
| Cashew                  | `cashew.png`       | <a href="https://www.flaticon.com/free-icons/cashew" title="cashew icons">Cashew icons created by Magnific - Flaticon</a>             |
| Chanterelle             | `chanterelle.png`  | <a href="https://www.flaticon.com/free-icons/mushroom" title="mushroom icons">Mushroom icons created by Magnific - Flaticon</a>       |
| Clam Rock               | `clam_rock.png`    | <a href="https://www.flaticon.com/free-icons/shell-link" title="shell link icons">Shell link icons created by Magnific - Flaticon</a> |
| Coconut                 | `coconut.png`      | <a href="https://www.flaticon.com/free-icons/coconut" title="coconut icons">Coconut icons created by Magnific - Flaticon</a>          |
| Crimson Apol            | `crimson_apol.png` | <a href="https://www.flaticon.com/free-icons/plant" title="plant icons">Plant icons created by Magnific - Flaticon</a>                |
| Fiddlehead              | `fiddlehead.png`   | <a href="https://www.flaticon.com/free-icons/fern" title="fern icons">Fern icons created by Magnific - Flaticon</a>                   |
| Fireweed                | `fireweed.png`     | <a href="https://www.flaticon.com/free-icons/flower" title="flower icons">Flower icons created by Magnific - Flaticon</a>             |
| Jackfruit               | `jackfruit.png`    | <a href="https://www.flaticon.com/free-icons/jackfruit" title="jackfruit icons">Jackfruit icons created by Magnific - Flaticon</a>    |
| Mango                   | `mango.png`        | <a href="https://www.flaticon.com/free-icons/mango" title="mango icons">Mango icons created by Magnific - Flaticon</a>                |
| Marigold                | `marigold.png`     | <a href="https://www.flaticon.com/free-icons/petals" title="petals icons">Petals icons created by Magnific - Flaticon</a>             |
| Melon                   | `melon.png`        | <a href="https://www.flaticon.com/free-icons/melon" title="melon icons">Melon icons created by Magnific - Flaticon</a>                |
| Orange                  | `orange.png`       | <a href="https://www.flaticon.com/free-icons/fruit" title="fruit icons">Fruit icons created by Magnific - Flaticon</a>                |
| Papaya                  | `papaya.png`       | <a href="https://www.flaticon.com/free-icons/papaya" title="papaya icons">Papaya icons created by Magnific - Flaticon</a>             |
| Potato                  | `potato.png`       | <a href="https://www.flaticon.com/free-icons/potato" title="potato icons">Potato icons created by Magnific - Flaticon</a>             |
| Potato Vine             | `potato_vine.png`  | <a href="https://www.flaticon.com/free-icons/potato" title="potato icons">Potato icons created by Magnific - Flaticon</a>             |
| Pumpkin                 | `pumpkin.png`      | <a href="https://www.flaticon.com/free-icons/pumpkin" title="pumpkin icons">Pumpkin icons created by Magnific - Flaticon</a>          |
| Radish                  | `radish.png`       | <a href="https://www.flaticon.com/free-icons/radish" title="radish icons">Radish icons created by Magnific - Flaticon</a>             |
| Red Currant             | `red_currant.png`  | <a href="https://www.flaticon.com/free-icons/currant" title="currant icons">Currant icons created by Magnific - Flaticon</a>          |
| Russula                 | `russula.png`      | <a href="https://www.flaticon.com/free-icons/mushroom" title="mushroom icons">Mushroom icons created by Magnific - Flaticon</a>       |
| Sumac                   | `sumac.png`        | <a href="https://www.flaticon.com/free-icons/berries" title="berries icons">Berries icons created by Magnific - Flaticon</a>          |
| Sunchoke                | `sunchoke.png`     | <a href="https://www.flaticon.com/free-icons/flower" title="flower icons">Flower icons created by Magnific - Flaticon</a>             |
| Trillium                | `trillium.png`     | <a href="https://www.flaticon.com/free-icons/flower" title="flower icons">Flower icons created by Magnific - Flaticon</a>             |
| Violet Apol             | `violet_apol.png`  | <a href="https://www.flaticon.com/free-icons/flower" title="flower icons">Flower icons created by Magnific - Flaticon</a>             |

### Icons for gastroliths

| File name            | Source                                                                                                                                      |
| ---------------------|---------------------------------------------------------------------------------------------------------------------------------------------|
| `gastrolith.png`     | <a href="https://www.flaticon.com/free-icons/rocks" title="rocks icons">Rocks icons created by Magnific - Flaticon</a>                      |


### Icons for salt licks

| File name            | Source                                                                                                                                      |
| ---------------------|---------------------------------------------------------------------------------------------------------------------------------------------|
| `salt_lick.png`      | <a href="https://www.flaticon.com/free-icons/pepper" title="pepper icons">Pepper icons created by Magnific - Flaticon</a>                   |

