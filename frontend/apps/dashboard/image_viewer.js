import m from "mithril";
import {Modal} from "./bootstrap/modal";

import {checkAnimationsDisabled, reflow} from "../../src/util";
import Card from "@polyfile/core/ui-kit/card";

const WHEEL_ZOOM = 0.5
const SLIDE_OFFSET = 30;

// Scale limits
const MIN_SCALE = 1;
const MAX_SCALE = 4;

// Transition classes
const CLASS_NAME_END = 'carousel-item-end'
const CLASS_NAME_START = 'carousel-item-start'
const CLASS_NAME_NEXT = 'carousel-item-next'
const CLASS_NAME_PREV = 'carousel-item-prev'

let isSliding = false;

function Point(x, y) {
  this.x = x;
  this.y = y;
}

function ImageViewerImage(fs_node) {
  this.fs_node = fs_node;
  this.is_valid = fs_node.mime_type.startsWith("image/");
}

const ImageViewerItem = {
  view(vnode) {
    const {image, currentMove, currentScale, isActive} = vnode.attrs;

    return (
      m(".d-flex h-100", image.is_valid
        && m("img.d-block", {
          draggable: false,
          src: image.fs_node.download_url,
          alt: image.fs_node.name,
          style: isActive && {
            transform: `translate(${currentMove.x}px, ${currentMove.y}px) scale(${currentScale})`,
          } || null,
          onerror: () => {
            image.is_valid = false;
          }
        })
        || m(".col-md-5 p-lg-5 m-auto",
          m(Card, {
            title: image.fs_node.name,
            style: isActive && {
              left: `${currentMove.x}px`,
            } || null,
          }, [
            m("h4", "Preview is not available"),
            m("p", "You can download this file"),
            m("a.btn btn-primary me-md-2", {
              class: image.fs_node.download_url ? "" : "disabled",
              href: m.buildPathname(image.fs_node.download_url || "#", {
                disposition: "attachment",
              }),
            }, "Download"),
          ])
        )
      )
    )
  }
};

/*
* Return the previous/next element of a list.
*/
const getNextElementIndex = (itemsLength, currentIndex, isNext) => {
  let nextIndex = (currentIndex + (isNext ? 1 : -1)) % itemsLength;
  if (nextIndex < 0) {nextIndex = itemsLength - 1}
  return nextIndex;
}

/*
* Buttons to go to previous/next element.
* */
const ImageViewerButton = {
  view(vnode) {
    return (
      m("button.d-none d-sm-block z-0 bg-black[type=button]", {
        class: vnode.attrs.class,
        onclick: (e) => {
          e.preventDefault();
          if (!isSliding) {
            vnode.attrs.slide();
          }
        },
      }, vnode.children)
    )
  }
};

/*
* Check if element is inside bounding box.
* */
const checkImgFits = (imgSize, parentSize, currentMove) => {
  // There is no need to shift the image if it fits within the parent element
  if (imgSize > parentSize) {
    // Check one side
    const move = Math.min((imgSize - parentSize) / 2, currentMove);
    // Check another side
    return Math.max((parentSize - imgSize) / 2, move);
  }
  return 0;
}

/*
* Modal for image viewer.
* */
const ImageViewerModal = {
  // Disable backdrop because modal is fullscreen
  backdrop: false,

  oninit(vnode) {
    if (!vnode.attrs.currentImg) {
      throw new Error("Argument 'currentImg' is required")
    }
    const items = vnode.attrs.items || [vnode.attrs.currentImg];

    vnode.state.images = items.map((item) => new ImageViewerImage(item));
    vnode.state.currentImg = vnode.state.images.find(item => item.fs_node === vnode.attrs.currentImg);
    vnode.state.itemsEl = [];

    // Image transform
    vnode.state.currentScale = MIN_SCALE;
    // TODO: zoom into cursor
    vnode.state.currentMove = new Point(0, 0);
    vnode.state.prevMove = new Point(0, 0);
    vnode.state.initialEvPos = new Point(0, 0);

    // Zoom detection (including multipoint configurations)
    // TODO: maybe evCache is not needed
    vnode.state.evCache = [];
    vnode.state.prevDiff = -1;
    vnode.state.initialScale = 0;
    vnode.state.wasZoomed = false;
  },

  // Get current image element. Can return non-img element if image not valid.
  getCurrentImgEl(vnode) {
    const currentIndex = vnode.state.images.indexOf(vnode.state.currentImg);
    const el = vnode.state.itemsEl[currentIndex];
    return el.querySelector('img') || el.firstChild;
  },

  // Check if image element fits inside bounding box.
  checkImgElFits(vnode, allowXOverflow=false) {
    const {currentMove, currentScale} = vnode.state;
    const currentImgEl = this.getCurrentImgEl(vnode);
    const parentElementEl = currentImgEl.parentElement;

    if (!allowXOverflow) {
      currentMove.x = checkImgFits(currentImgEl.offsetWidth * currentScale, parentElementEl.offsetWidth, currentMove.x);
    }
    currentMove.y = checkImgFits(currentImgEl.offsetHeight * currentScale, parentElementEl.offsetHeight, currentMove.y);
  },

  // Slide to previous/next image
  slide(vnode, isNext) {
    const {currentMove, images, itemsEl} = vnode.state;
    const currentIndex = images.indexOf(vnode.state.currentImg);
    const nextIndex = getNextElementIndex(images.length, currentIndex, isNext);

    if (currentIndex === nextIndex) {return}

    currentMove.y = 0;
    vnode.state.currentScale = 1;

    if (checkAnimationsDisabled()) {
      vnode.state.currentImg = images[nextIndex];
      return;
    }

    // Carousel elements (not images)
    const activeElement = itemsEl[currentIndex];
    const nextElement = itemsEl[nextIndex];
    const directionalClassName = isNext ? CLASS_NAME_START : CLASS_NAME_END
    const orderClassName = isNext ? CLASS_NAME_NEXT : CLASS_NAME_PREV

    isSliding = true;
    nextElement.classList.add(orderClassName)
    reflow(nextElement)
    activeElement.classList.add(directionalClassName)
    nextElement.classList.add(directionalClassName)
  },

  setCurrentScale(vnode, newScale) {
    const {currentMove} = vnode.state;

    vnode.state.currentScale = Math.min(MAX_SCALE, Math.max(MIN_SCALE, newScale));

    // Reset pan position when zooming out to full size
    if (vnode.state.currentScale === MIN_SCALE) {
      currentMove.x = 0;
      currentMove.y = 0;
    } else {
      this.checkImgElFits(vnode);
    }
  },

  pointerUpEvent(vnode, ev) {
    const {evCache, currentScale, currentMove} = vnode.state;
    // Remove this event from the target's cache
    const index = evCache.findIndex(
      (cachedEv) => cachedEv.pointerId === ev.pointerId,
    );
    evCache.splice(index, 1);

    if (evCache.length === 0 && !isSliding) {
      const currentImgEl = this.getCurrentImgEl(vnode);
      if (!currentImgEl) {return}
      const parentHeight = currentImgEl.parentElement.offsetHeight;
      const currentHeight = currentImgEl.offsetHeight * currentScale;

      if (currentHeight <= parentHeight) {
        if (Math.abs(currentMove.x) > SLIDE_OFFSET && !vnode.state.wasZoomed) {
          this.slide(vnode, currentMove.x < 0);
        } else {
          currentMove.x = 0;
        }
      }
      vnode.state.wasZoomed = false;
    }

    // If the number of pointers down is less than two then reset diff tracker
    if (evCache.length < 2) {
      vnode.state.prevDiff = -1;
    }
  },

  wheelEvent(vnode, ev) {
    // Mouse wheel event
    ev.preventDefault();
    const {currentScale, currentImg} = vnode.state;
    if (!currentImg.is_valid) {return}

    if (!isSliding) {
      this.setCurrentScale(vnode, ev.deltaY > 0 ? currentScale - WHEEL_ZOOM : currentScale + WHEEL_ZOOM)
    }
  },

  pointerDownEvent(vnode, ev) {
    const {evCache, currentScale, prevMove, initialEvPos, currentMove} = vnode.state;
    evCache.push(ev);
    vnode.state.initialScale = currentScale;
    initialEvPos.x = ev.clientX;
    initialEvPos.y = ev.clientY;
    prevMove.x = currentMove.x;
    prevMove.y = currentMove.y;
  },

  pointerMoveEvent(vnode, ev) {
    const {evCache, currentScale, prevDiff, prevMove, initialEvPos, currentMove, currentImg} = vnode.state;

    // If one pointer is down - move image
    if (evCache.length === 1 && !isSliding) {
      const currentImgEl = this.getCurrentImgEl(vnode);
      const parentElementEl = currentImgEl.parentElement;

      const currentHeight = currentImgEl.offsetHeight * currentScale;
      const parentHeight = parentElementEl.offsetHeight;

      currentMove.y = prevMove.y + (ev.clientY - initialEvPos.y);
      currentMove.x = prevMove.x + (ev.clientX - initialEvPos.x);
      const readyForSlide = currentHeight > parentHeight;
      this.checkImgElFits(vnode, !readyForSlide);
    }

    // Find this event in the cache and update its record with this event
    const index = evCache.findIndex(
      (cachedEv) => cachedEv.pointerId === ev.pointerId,
    );
    evCache[index] = ev;

    // Multitouch handling
    if (evCache.length === 2 && !isSliding) {
      // Ignore invalid images
      if (!currentImg.is_valid) {return}

      // If two pointers are down, check for pinch gestures
      // Calculate the distance between the two pointers
      const curDiff = Math.hypot(
        evCache[0].clientX - evCache[1].clientX,
        evCache[0].clientY - evCache[1].clientY,
      );

      if (prevDiff > 0) {
        const scaleFactor = curDiff / prevDiff;
        this.setCurrentScale(vnode, currentScale * scaleFactor)
      }

      // Cache the distance for the next move event
      vnode.state.prevDiff = curDiff;
      vnode.state.wasZoomed = true;
    }
  },

  imgTransitionEnd(vnode, image, ev) {
    // If transform (sliding) is complete we should check if image has changed
    if (
      isSliding
      && ev.propertyName === "transform"
      && ev.target.classList.contains("carousel-item")
      && vnode.state.currentImg !== image
    ) {
      vnode.state.currentImg = image;
      // Reset variables
      isSliding = false;
      vnode.state.currentMove.x = 0;
      vnode.state.currentMove.y = 0;
      vnode.state.currentScale = MIN_SCALE;
      vnode.state.wasZoomed = false;
    }
  },

  view(vnode) {
    return (
      m(Modal, {fade: false, ...vnode.attrs},
        m(".image-viewer-modal modal-dialog modal-fullscreen",
          m(".modal-content", [
            m(".modal-header position-absolute top-0 start-0 w-100 z-1 bg-white bg-opacity-75", {
              class: vnode.state.currentScale > 1 ? "d-none" : null,
            }, [
              m("span.modal-title", isSliding && m.trust("&nbsp;") || vnode.state.currentImg.fs_node.name),
              m(Modal.modalCloseButton, vnode.attrs),
            ]),
            m(".modal-body",
              m(".carousel slide w-100", {
                  // Mouse event handling
                  onwheel: this.wheelEvent.bind(this, vnode),
                  // Multipoint touch zoom / swipe
                  onpointerdown: this.pointerDownEvent.bind(this, vnode),
                  onpointerup: this.pointerUpEvent.bind(this, vnode),
                  onpointercancel: this.pointerUpEvent.bind(this, vnode),
                  onpointerleave: this.pointerUpEvent.bind(this, vnode),
                  onpointermove: this.pointerMoveEvent.bind(this, vnode),
                }, [
                  m(".carousel-inner", vnode.state.images.map(
                    (image, index) => m(".carousel-item", {
                      class: vnode.state.currentImg === image ? "active" : "",
                      oncreate(v) {
                        vnode.state.itemsEl[index] = v.dom;
                      },
                      ontransitionend: this.imgTransitionEnd.bind(this, vnode, image),
                    }, m(ImageViewerItem, {
                      image,
                      isActive: vnode.state.currentImg === image,
                      currentMove: vnode.state.currentMove,
                      currentScale: vnode.state.currentScale,
                    }))
                  )),
                  m(ImageViewerButton, {slide: () => this.slide(vnode, false), class: "carousel-control-prev"}, [
                    m("span.carousel-control-prev-icon[aria-hidden=true]"),
                    m("span.visually-hidden", "Previous"),
                  ]),
                  m(ImageViewerButton, {slide: () => this.slide(vnode, true), class: "carousel-control-next"}, [
                    m("span.carousel-control-next-icon[aria-hidden=true]"),
                    m("span.visually-hidden", "Next"),
                  ]),
                ]
              )
            )
          ])
        )
      )
    )
  }
}

export default ImageViewerModal;
