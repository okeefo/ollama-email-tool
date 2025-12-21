package main

import (
	"fmt"
	"log"
	"os"
	"sync"
	"sync/atomic"
	"time"

	imap "github.com/emersion/go-imap/v2"
	"github.com/emersion/go-imap/v2/imapclient"
	"github.com/joho/godotenv"
)

var completedCount uint64
var total uint64

func main() {
	godotenv.Load("../.env")
	user := os.Getenv("GMAIL_USER")
	pass := os.Getenv("GMAIL_APP_PASSWORD")
	storageDir := "/srv/storage/docker/email_data/raw_emails"

	// Ensure directory exists
	if err := os.MkdirAll(storageDir, 0755); err != nil {
		log.Fatalf("failed to create storage directory %q: %v", storageDir, err)
	}

	// 1. Initial connection to get the IDs
	c, err := imapclient.DialTLS("imap.gmail.com:993", nil)
	if err != nil {
		log.Fatalf("failed to dial IMAP server: %v", err)
	}
	if err := c.Login(user, pass).Wait(); err != nil {
		log.Fatalf("failed to login: %v", err)
	}
	if _, err := c.Select("INBOX", nil).Wait(); err != nil {
		log.Fatalf("failed to select INBOX: %v", err)
	}

	threeMonthsAgo := time.Now().AddDate(0, -3, 0)
	criteria := &imap.SearchCriteria{Before: threeMonthsAgo}
	searchData, err := c.Search(criteria, nil).Wait()
	if err != nil {
		log.Fatalf("search failed: %v", err)
	}
	ids := searchData.AllSeqNums()
	total = uint64(len(ids))
	if err := c.Logout().Wait(); err != nil {
		log.Printf("logout error: %v", err)
	}

	fmt.Printf("Found %d emails. Starting worker pool...\n", len(ids))

	// 2. Setup Worker Pool
	idChan := make(chan uint32, len(ids))
	var wg sync.WaitGroup
	numWorkers := 15 // Increased worker count per request

	for w := 1; w <= numWorkers; w++ {
		wg.Add(1)
		go worker(w, idChan, user, pass, storageDir, &wg)
	}

	// 3. Feed the IDs into the channel
	for _, id := range ids {
		idChan <- id
	}
	close(idChan) // Workers will stop when channel is empty

	wg.Wait()
	fmt.Println("\nAll workers finished.")
}

func worker(id int, ids <-chan uint32, user, pass, dir string, wg *sync.WaitGroup) {
	defer wg.Done()

	// Each worker opens ONE connection
	c, err := imapclient.DialTLS("imap.gmail.com:993", nil)
	if err != nil {
		log.Printf("Worker %d failed to connect: %v", id, err)
		return
	}
	defer func() {
		if err := c.Logout().Wait(); err != nil {
			log.Printf("Worker %d logout error: %v", id, err)
		}
	}()
	if err := c.Login(user, pass).Wait(); err != nil {
		log.Printf("Worker %d login failed: %v", id, err)
		return
	}
	if _, err := c.Select("INBOX", nil).Wait(); err != nil {
		log.Printf("Worker %d select failed: %v", id, err)
		return
	}

	for seqNum := range ids {
		section := &imap.FetchItemBodySection{}
		fetchOptions := &imap.FetchOptions{
			BodySection: []*imap.FetchItemBodySection{section},
		}

		cmd := c.Fetch(imap.SeqSetNum(seqNum), fetchOptions)
		msg := cmd.Next()
		if msg == nil {
			// Ensure command is closed before continuing
			_ = cmd.Close()
			continue
		}

		buf, err := msg.Collect()
		if err != nil {
			log.Printf("Worker %d collect failed for %d: %v", id, seqNum, err)
			_ = cmd.Close()
			continue
		}
		bodyBytes := buf.FindBodySection(section)
		if bodyBytes == nil {
			log.Printf("Worker %d no body for %d", id, seqNum)
			_ = cmd.Close()
			continue
		}

		// Save to disk
		filename := fmt.Sprintf("%s/%d.eml", dir, seqNum)
		if err := os.WriteFile(filename, bodyBytes, 0644); err != nil {
			log.Printf("Worker %d write failed for %s: %v", id, filename, err)
			_ = cmd.Close()
			continue
		}

		// Close the fetch command for this iteration
		if err := cmd.Close(); err != nil {
			log.Printf("Worker %d fetch close error for %d: %v", id, seqNum, err)
		}

		// Progress: atomic increment and periodic status
		newCount := atomic.AddUint64(&completedCount, 1)
		if newCount%100 == 0 {
			fmt.Printf("\rProgress: %d / %d (%.2f%%)", newCount, total, float64(newCount)/float64(total)*100)
		}
	}
}
