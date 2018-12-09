#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include "bmp.h"

//BMP header//
struct BmpHeader {

	char ident[2];
	char file_size[4];
	char reserve_1[2];
	char reserve_2[2];
	char pix_array_offset[4];
};

//DIB Header//
struct BITMAPINFOHEADER {
	
	char size[4];
	char width[4];
	char height[4];
	char colour_plain[2];
	char bbp[2];			//colour depth
	char compression_method[4];
	char img_size[4]; 		//raw bitmap size
	char horizontal_res[4]; 
	char vertical_res[4]; 
	char num_colours[4]; 		//colours in colour palette
	char important_colours[4]; 
};

//file header info
struct BmpHeader t;
struct BITMAPINFOHEADER dib;

//rrheingans-yoo added 2018-12-02
//write image to file
void write_image(struct image *img, const char *file_name) {
	FILE *fp;
	fp = fopen(file_name,"wb");
	
	if (fp == NULL) {
	
		//printf("error opening file");
		//return NULL;
	}
	
	/* read-in logic
	
	//read file headers
	fread (&t, sizeof(struct BmpHeader), 1, fp);
	fread (&dib, sizeof(struct BITMAPINFOHEADER), 1, fp);
	fclose(fp);
	
	//get pixel data from file and copy it into the buffer 
	fp = fopen(file_name,"rb");
	fseek(fp,pix_array_offset[0],SEEK_SET);
	fread (img->pixel_array, *img_size, 1, fp);
	fclose(fp);
	
	*/
	
	convert_to_rgb(img);
	reverse_pixel_array(img);
	
	fwrite (&t, sizeof(struct BmpHeader), 1, fp);
	fwrite (&dib, sizeof(struct BITMAPINFOHEADER), 1, fp);
	fseek (fp,*(uint32_t*)&t.pix_array_offset,SEEK_SET);
	fwrite (img->pixel_array, *(uint32_t*)&dib.img_size, 1, fp);
	
	convert_to_rgb(img);
	reverse_pixel_array(img);
}

struct image* load_bmp(const char *file_name) {

	struct image *img;
	
	img = malloc(sizeof(struct image));
	
	if (img == NULL) {
	
		//printf("error allocating memory for image structure");
		return NULL;
	}

	//image file to process
	FILE *fp;
	fp = fopen(file_name,"rb");

	if (fp == NULL) {
	
		//printf("error opening file");
		return NULL;
	}

	//read file headers
	fread (&t, sizeof(struct BmpHeader), 1, fp);	

	if (t.ident[0] != 'B' && t.ident[1] != 'M') {

		//printf("Invalid BMP file header");
		return NULL;
	}

	fread (&dib, sizeof(struct BITMAPINFOHEADER), 1, fp);	
	fclose(fp);

	//convert file header info to appropriate types
	uint32_t *pix_array_offset = (uint32_t*)&t.pix_array_offset;
	uint32_t *img_width = (uint32_t*)&dib.width;
	uint32_t *img_height = (uint32_t*)&dib.height;
	uint32_t *img_size = (uint32_t*)&dib.img_size;
	uint16_t *bbp = (uint16_t*)&dib.bbp;

	//24bit pixels only (bytes)
	unsigned int row_size = (*bbp / 8) * *img_width;

	//padding size (bytes)
	unsigned int padding = *img_width % 4;

	//populate image struct	
	img->padding = padding;
	img->row_length = row_size;
	img->width = *img_width;
	img->height = *img_height;
	img->pixel_array_size = *img_size;
    img->bbp = *bbp;

	//allocate the pixel buffer
	img->pixel_array = malloc(*img_size);
	
	//get pixel data from file and copy it into the buffer 
	fp = fopen(file_name,"rb");
	fseek(fp,pix_array_offset[0],SEEK_SET);
	fread (img->pixel_array, *img_size, 1, fp);	
	fclose(fp);

	//convert the pixel array in-place from bgr colour space to rgb color space
	convert_to_rgb(img);

	//reverse pixel array
	reverse_pixel_array(img);

    if (img->bbp > 24)  //Warn user if they load an image with a higher than 24bit bbp.
    {
        printf("You have loaded a bmp with a higher than 24bit colourdepth.\nSome things may not behave correctly.\n");
    }

	return img;	
}

//free the pixel data from memory
void free_image(struct image *img) {
	free(img->pixel_array);
	free(img);
}

//print out pixel data to std out omitting padded bytes for debugging purposes
void print_pixel_array(struct image *img) {

	int i;
	int row_pos = 0;

	//Loop through the whole pixel array
	for (i = 0; i < img->pixel_array_size; i++) {

		//print a new line after each row of pixels
		// skip the loop count ahead of the padded bytes
		if (row_pos == img->row_length) {
		
			printf("\n");
			row_pos = 0; 			//reset the row count.
			i = i + img->padding - 1; 	//skip padding, minus 1 because
			continue;   			//for condition will add 1 to i;
		}

		printf("%d. rgb[%d]\n", i, img->pixel_array[i]);
		
		//advance the position we are in the row, so we know when we can skip the padding bytes
		row_pos++;	
	}
}

//convert the pixel array in-place from blue, green, red colour space, to the red, green, blue colour space
void convert_to_rgb(struct image *img) {
	
	int i;
	int row_pos = 0;
	int flag = 0;
	unsigned char temp = 0;
	enum colour {BLUE, GREEN, RED};

	//Loop through the whole pixel array
	for (i = 0; i < img->pixel_array_size; i++) {

		// skip the loop count ahead of the padded bytes
		if (row_pos == img->row_length) {
		
			row_pos = 0; 			//reset the row position count.
			i = i + img->padding - 1; 	//skip padding, minus 1 because
			continue;   			//for condition will add 1 to i;
		}

		//put the blue value into a temp variable
		if (flag == BLUE) {
			
			temp = img->pixel_array[i];
			flag = GREEN; // change flag to GREEN for processing the green value

		//green is already in place don't need to do anything
		} else if( flag == GREEN) {
			
			flag = RED;// change flag to RED for processing the red value

		//put the red value into the blue's old place. and the temp value in the red's place
		} else if (flag == RED) {
			
			img->pixel_array[i - 2] = img->pixel_array[i];
			img->pixel_array[i] = temp;
			flag = BLUE; // reset flag back to BLUE to start the cycle again.
		}

		//advance the position we are in the row, so we know when we can skip the padding bytes
		row_pos++;	
	}
}

//this reverses the pixel array because BMP files by definition are stored upside down
//possible optimisation using memcpy() function instead of swapping byte for byte.
void reverse_pixel_array(struct image *img) {

	int i;
	int temp = 0;
	int row_pos = 0; //byte position in current row
	int row_count = 1; //we always start from the 1st row
	int opposite_row_i = (img->row_length + img->padding) * (img->height - row_count); //the array index opposite to the current index

	//Loop through the whole pixel array
	for (i = 0; i < img->pixel_array_size / 2; i++) {

		// skip the loop count ahead of the padded bytes
		// put index counters at their correct positions so the algorithm works correctly
		if (row_pos == img->row_length) {
			
			//which row in the image we are at
			row_count++;
			
			//the index to the start of the opposite row to the current row index	
			opposite_row_i = (img->row_length + img->padding) * (img->height - row_count);

			//reset the row position count. (which byte in the current row we're at)
			row_pos = 0;

			//skip padding, minus 1 because the for condition will add 1 to the index;
			i = i + img->padding - 1; 			
			continue;		
		}
	
		//swap one row of pixels with the opposite row. eg first row with last row. second with second last
		temp = img->pixel_array[i];
		img->pixel_array[i] = img->pixel_array[opposite_row_i];	
		img->pixel_array[opposite_row_i] = temp;
		opposite_row_i++;		

		//advance the position we are in the row, so we know when we can skip the padding bytes
		row_pos++;	
	}
}


//This returns the bbp of the loaded image as an integer.
//uses a 32bit int to avoid integer overflow.
uint16_t get_colour_depth(struct image *img)
{

    uint32_t depth = img->bbp;

    
    return depth;
}

